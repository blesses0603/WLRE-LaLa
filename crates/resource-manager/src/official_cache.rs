//! 以官方清單的 MD5 與 CRC32 驗證傳輸錯誤；不提供密碼學防竄改保證。
use crate::{
    bundle_index::Bundle,
    verified_cache,
    version_map::{self, Platform},
};
use md5::{Digest, Md5};
use sha2::Sha256;
use std::{
    io::{Read, Write},
    path::{Path, PathBuf},
};
pub use wlre_core_observability::ErrorCode as CacheError;
const MAX_BYTES: u64 = 256 * 1024 * 1024;

#[derive(Debug)]
pub struct CachedBundle {
    pub path: PathBuf,
    pub local_sha256: String,
    pub downloaded: bool,
}

/// 從固定官方 HTTPS 主機下載清單列出的封包，使用大小、MD5、CRC32 小端驗證。
/// 必須提供可信、私有、單一寫入者的快取根目錄。MD5／CRC 僅檢查損毀，
/// 不保證抵抗惡意替換；本地 SHA-256 只是快取識別，不是獨立簽章。
/// 呼叫端必須從目前官方快照取得條目並在使用前後重新檢查版本。
pub(crate) fn fetch(
    client: &reqwest::blocking::Client,
    root: &Path,
    platform: Platform,
    version: &str,
    bundle: &Bundle,
) -> Result<CachedBundle, CacheError> {
    if !version_map::valid_version(version) {
        return Err(CacheError::VersionMappingUnknown);
    }
    verified_cache::validate_name(&bundle.bundle_name)?;
    if bundle.encrypted {
        return Err(CacheError::UnsupportedEncryption);
    }
    let dir = match platform {
        Platform::Windows => "ResourcesPC",
        Platform::Android => "ResourcesAndroid",
    };
    let url = format!(
        "https://wlreftpsrc.chinesegamer.net/WLN/TW/{version}/{dir}/AssetBundle/{}",
        bundle.bundle_name
    );
    fetch_from(client, &url, root, bundle)
}

pub(crate) fn check_input(bundle: &Bundle) -> Result<(String, String), CacheError> {
    if bundle.file_size == 0 || bundle.file_size > MAX_BYTES {
        return Err(CacheError::CacheTooLarge);
    }
    if bundle.file_hash.len() != 32
        || !bundle.file_hash.bytes().all(|b| b.is_ascii_hexdigit())
        || bundle.file_crc.len() != 8
        || !bundle.file_crc.bytes().all(|b| b.is_ascii_hexdigit())
    {
        return Err(CacheError::IndexInvalidEntry);
    }
    Ok((
        bundle.file_hash.to_ascii_lowercase(),
        bundle.file_crc.to_ascii_lowercase(),
    ))
}
fn check_stream(
    mut input: impl Read,
    mut output: impl Write,
    bundle: &Bundle,
) -> Result<String, CacheError> {
    let (md5_expected, crc_expected) = check_input(bundle)?;
    let mut md5 = Md5::new();
    let mut sha = Sha256::new();
    let mut crc = crc32fast::Hasher::new();
    let mut total = 0u64;
    let mut buf = [0u8; 16384];
    loop {
        let n = input
            .read(&mut buf)
            .map_err(|_| CacheError::StorageFailure)?;
        if n == 0 {
            break;
        }
        total = total
            .checked_add(n as u64)
            .ok_or(CacheError::CacheTooLarge)?;
        if total > bundle.file_size || total > MAX_BYTES {
            return Err(CacheError::CacheTooLarge);
        }
        md5.update(&buf[..n]);
        sha.update(&buf[..n]);
        crc.update(&buf[..n]);
        output
            .write_all(&buf[..n])
            .map_err(|_| CacheError::StorageFailure)?;
    }
    let actual_crc: String = crc
        .finalize()
        .to_le_bytes()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect();
    if total != bundle.file_size
        || format!("{:x}", md5.finalize()) != md5_expected
        || actual_crc != crc_expected
    {
        return Err(CacheError::CacheIntegrityFailure);
    }
    Ok(format!("{:x}", sha.finalize()))
}
fn fetch_from(
    client: &reqwest::blocking::Client,
    url: &str,
    root: &Path,
    bundle: &Bundle,
) -> Result<CachedBundle, CacheError> {
    let (md5, crc) = check_input(bundle)?;
    if !std::fs::symlink_metadata(root)
        .map_err(|_| CacheError::StorageFailure)?
        .file_type()
        .is_dir()
    {
        return Err(CacheError::CacheInvalidInput);
    }
    let target = root.join(format!("official-{md5}-{crc}-{}", bundle.file_size));
    match std::fs::symlink_metadata(&target) {
        Ok(meta) => {
            if !meta.file_type().is_file() {
                return Err(CacheError::CacheInvalidInput);
            }
            if meta.len() == bundle.file_size {
                let file = std::fs::File::open(&target).map_err(|_| CacheError::StorageFailure)?;
                if let Ok(sha) = check_stream(file, std::io::sink(), bundle) {
                    return Ok(CachedBundle {
                        path: target,
                        local_sha256: sha,
                        downloaded: false,
                    });
                }
            }
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
        Err(_) => return Err(CacheError::StorageFailure),
    }
    let response = client
        .get(url)
        .send()
        .map_err(|_| CacheError::RequestFailed)?;
    if response.status() != reqwest::StatusCode::OK {
        return Err(CacheError::UnexpectedResponse);
    }
    if response
        .content_length()
        .is_some_and(|n| n != bundle.file_size)
    {
        return Err(CacheError::CacheIntegrityFailure);
    }
    let mut tmp = tempfile::NamedTempFile::new_in(root).map_err(|_| CacheError::StorageFailure)?;
    let sha = check_stream(response, tmp.as_file_mut(), bundle)?;
    tmp.as_file_mut()
        .sync_all()
        .map_err(|_| CacheError::StorageFailure)?;
    tmp.persist(&target)
        .map_err(|_| CacheError::StorageFailure)?;
    Ok(CachedBundle {
        path: target,
        local_sha256: sha,
        downloaded: true,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn bundle(data: &[u8]) -> Bundle {
        Bundle {
            bundle_name: "sample.bundle".into(),
            unity_crc: 0,
            file_hash: format!("{:x}", Md5::digest(data)),
            file_crc: crc32fast::hash(data)
                .to_le_bytes()
                .iter()
                .map(|b| format!("{b:02x}"))
                .collect(),
            file_size: data.len() as u64,
            encrypted: false,
            tags: vec![],
            depend_ids: vec![],
        }
    }
    #[test]
    #[ignore = "需對官方固定端點讀取一個小型封包至暫存目錄"]
    fn official_bundle_cache_smoke() {
        let snapshot = crate::manifest_snapshot::fetch(Platform::Windows, "1.3.0").unwrap();
        let all =
            crate::auto_update::prepare_bundles(&snapshot, 10_000, 8 * 1024 * 1024 * 1024).unwrap();
        assert!(!all.is_empty());
        let item = snapshot
            .data
            .bundle_list
            .iter()
            .find(|b| b.bundle_name == "datapackage_data_v.bundle")
            .unwrap();
        let root = tempfile::tempdir().unwrap();
        let client = reqwest::blocking::Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .timeout(std::time::Duration::from_secs(30))
            .build()
            .unwrap();
        let first = fetch(
            &client,
            root.path(),
            Platform::Windows,
            &snapshot.data_version,
            item,
        )
        .unwrap();
        assert!(first.downloaded);
        let second = fetch(
            &client,
            root.path(),
            Platform::Windows,
            &snapshot.data_version,
            item,
        )
        .unwrap();
        assert!(!second.downloaded);
        assert_eq!(first.local_sha256, second.local_sha256);
    }

    #[test]
    fn validates_official_little_endian_checksum_and_size() {
        let data = b"synthetic";
        let entry = bundle(data);
        assert!(check_stream(&data[..], std::io::sink(), &entry).is_ok());
        let mut wrong = bundle(data);
        wrong.file_crc = "00000000".into();
        assert_eq!(
            check_stream(&data[..], std::io::sink(), &wrong),
            Err(CacheError::CacheIntegrityFailure)
        );
        let mut wrong = bundle(data);
        wrong.file_size += 1;
        assert_eq!(
            check_stream(&data[..], std::io::sink(), &wrong),
            Err(CacheError::CacheIntegrityFailure)
        );
    }
    #[test]
    fn rejects_bad_metadata_before_io() {
        let mut b = bundle(b"x");
        b.file_hash = "../bad".into();
        assert_eq!(check_input(&b), Err(CacheError::IndexInvalidEntry));
    }
    #[test]
    fn fetches_reuses_and_recovers_a_corrupted_cache() {
        use std::{net::TcpListener, thread, time::Duration};
        let data = b"synthetic";
        let entry = bundle(data);
        let root = tempfile::tempdir().unwrap();
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let server = thread::spawn(move || {
            for _ in 0..2 {
                let (mut s, _) = listener.accept().unwrap();
                s.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
                let mut req = Vec::new();
                let mut buf = [0; 256];
                while !req.ends_with(b"\r\n\r\n") {
                    let n = s.read(&mut buf).unwrap();
                    assert!(n > 0);
                    req.extend_from_slice(&buf[..n]);
                }
                write!(
                    s,
                    "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                    data.len()
                )
                .unwrap();
                s.write_all(data).unwrap();
            }
        });
        let client = reqwest::blocking::Client::builder()
            .no_proxy()
            .redirect(reqwest::redirect::Policy::none())
            .timeout(Duration::from_secs(3))
            .build()
            .unwrap();
        let url = format!("http://{address}/file");
        let first = fetch_from(&client, &url, root.path(), &entry).unwrap();
        assert!(first.downloaded);
        assert!(
            !fetch_from(&client, &url, root.path(), &entry)
                .unwrap()
                .downloaded
        );
        std::fs::write(&first.path, b"broken").unwrap();
        let repaired = fetch_from(&client, &url, root.path(), &entry).unwrap();
        assert!(repaired.downloaded);
        server.join().unwrap();
        assert_eq!(std::fs::read(repaired.path).unwrap(), data);
    }
}
