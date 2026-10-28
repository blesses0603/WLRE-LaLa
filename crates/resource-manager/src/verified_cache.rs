//! 受限封包下載與內容定址快取；預期雜湊須由可信來源提供。

use reqwest::blocking::Client;
use reqwest::redirect::Policy;
use sha2::{Digest, Sha256};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::time::Duration;
pub use wlre_core_observability::ErrorCode as CacheError;

const BASE: &str = "https://wlreftpsrc.chinesegamer.net/WLN/TW/1.3.22/ResourcesPC/AssetBundle/";
const MAX_BYTES: u64 = 64 * 1024 * 1024;

/// 快取物件識別必須是可信來源提供的 SHA-256，不可使用未確認的官方欄位充當。
/// 呼叫端須確保快取根目錄及其祖先是私有、可信且不受不可信程序修改。
/// 封包來源固定為已觀察的單一目錄；本函式不選擇官方版本或解包。
/// 已有物件會重新驗證；損毀時回傳錯誤，不覆寫該物件。
/// 預設串行執行，不自動重試；不處理排程及行動背景政策。
pub fn download_bundle(
    root: &Path,
    bundle_name: &str,
    expected_sha256: &str,
    size: u64,
) -> Result<PathBuf, CacheError> {
    let name = validate_name(bundle_name)?;
    let digest = validate_digest(expected_sha256)?;
    if size > MAX_BYTES {
        return Err(CacheError::CacheTooLarge);
    }
    let client = Client::builder()
        .redirect(Policy::none())
        .timeout(Duration::from_secs(60))
        .build()
        .map_err(|_| CacheError::RequestFailed)?;
    download_with_client(&client, &format!("{BASE}{name}"), root, &digest, size)
}

fn validate_name(name: &str) -> Result<&str, CacheError> {
    if name.is_empty()
        || name.len() > 200
        || name.ends_with('.')
        || name == "."
        || name == ".."
        || !name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
    {
        return Err(CacheError::CacheInvalidInput);
    }
    Ok(name)
}
fn validate_digest(value: &str) -> Result<String, CacheError> {
    if value.len() != 64 || !value.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err(CacheError::CacheInvalidInput);
    }
    Ok(value.to_ascii_lowercase())
}

fn digest_reader(
    mut input: impl Read,
    mut output: impl Write,
    size: u64,
) -> Result<String, CacheError> {
    let mut hash = Sha256::new();
    let mut total = 0_u64;
    let mut buffer = [0_u8; 16384];
    loop {
        let n = input
            .read(&mut buffer)
            .map_err(|_| CacheError::StorageFailure)?;
        if n == 0 {
            break;
        }
        total = total
            .checked_add(n as u64)
            .ok_or(CacheError::CacheTooLarge)?;
        if total > size || total > MAX_BYTES {
            return Err(CacheError::CacheTooLarge);
        }
        hash.update(&buffer[..n]);
        output
            .write_all(&buffer[..n])
            .map_err(|_| CacheError::StorageFailure)?;
    }
    if total != size {
        return Err(CacheError::CacheIntegrityFailure);
    }
    Ok(format!("{:x}", hash.finalize()))
}

fn verify_existing(path: &Path, digest: &str, size: u64) -> Result<bool, CacheError> {
    let metadata = match std::fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
        Err(_) => return Err(CacheError::StorageFailure),
    };
    if !metadata.file_type().is_file() || metadata.len() != size {
        return Err(CacheError::CacheIntegrityFailure);
    }
    let file = std::fs::File::open(path).map_err(|_| CacheError::StorageFailure)?;
    if digest_reader(file, std::io::sink(), size)? != digest {
        return Err(CacheError::CacheIntegrityFailure);
    }
    Ok(true)
}

fn download_with_client(
    client: &Client,
    url: &str,
    root: &Path,
    digest: &str,
    size: u64,
) -> Result<PathBuf, CacheError> {
    let root_metadata = std::fs::symlink_metadata(root).map_err(|_| CacheError::StorageFailure)?;
    if !root_metadata.file_type().is_dir() {
        return Err(CacheError::CacheInvalidInput);
    }
    let final_path = root.join(digest);
    if verify_existing(&final_path, digest, size)? {
        return Ok(final_path);
    }
    let response = client
        .get(url)
        .send()
        .map_err(|_| CacheError::RequestFailed)?;
    if response.status() != reqwest::StatusCode::OK {
        return Err(CacheError::UnexpectedResponse);
    }
    if response.content_length().is_some_and(|n| n != size) {
        return Err(CacheError::CacheIntegrityFailure);
    }
    let mut temporary =
        tempfile::NamedTempFile::new_in(root).map_err(|_| CacheError::StorageFailure)?;
    let actual = digest_reader(response, temporary.as_file_mut(), size)?;
    if actual != digest {
        return Err(CacheError::CacheIntegrityFailure);
    }
    temporary
        .as_file_mut()
        .sync_all()
        .map_err(|_| CacheError::StorageFailure)?;
    match temporary.persist_noclobber(&final_path) {
        Ok(_) => Ok(final_path),
        Err(error) if error.error.kind() == std::io::ErrorKind::AlreadyExists => {
            if verify_existing(&final_path, digest, size)? {
                Ok(final_path)
            } else {
                Err(CacheError::StorageFailure)
            }
        }
        Err(_) => Err(CacheError::StorageFailure),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;
    use std::thread;
    fn sha(bytes: &[u8]) -> String {
        format!("{:x}", Sha256::digest(bytes))
    }
    fn serve(body: &'static [u8]) -> (String, thread::JoinHandle<()>) {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let thread = thread::spawn(move || {
            let (mut socket, _) = listener.accept().unwrap();
            socket
                .set_read_timeout(Some(Duration::from_secs(3)))
                .unwrap();
            let mut req = Vec::new();
            let mut buf = [0; 256];
            while !req.ends_with(b"\r\n\r\n") {
                let n = socket.read(&mut buf).unwrap();
                assert!(n > 0);
                req.extend_from_slice(&buf[..n]);
            }
            write!(
                socket,
                "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                body.len()
            )
            .unwrap();
            socket.write_all(body).unwrap();
        });
        (format!("http://{address}/file"), thread)
    }
    fn client() -> Client {
        Client::builder()
            .no_proxy()
            .redirect(Policy::none())
            .timeout(Duration::from_secs(3))
            .build()
            .unwrap()
    }
    #[test]
    fn downloads_once_and_reuses_verified_content() {
        let root = tempfile::tempdir().unwrap();
        let data = b"synthetic";
        let digest = sha(data);
        let (url, server) = serve(data);
        let path =
            download_with_client(&client(), &url, root.path(), &digest, data.len() as u64).unwrap();
        server.join().unwrap();
        assert_eq!(std::fs::read(&path).unwrap(), data);
        assert_eq!(
            download_with_client(
                &client(),
                "http://127.0.0.1:1/",
                root.path(),
                &digest,
                data.len() as u64
            )
            .unwrap(),
            path
        );
    }
    #[test]
    fn rejects_corruption_without_publishing_or_overwriting() {
        let root = tempfile::tempdir().unwrap();
        let data = b"synthetic";
        let digest = sha(b"different");
        let (url, server) = serve(data);
        assert_eq!(
            download_with_client(&client(), &url, root.path(), &digest, data.len() as u64),
            Err(CacheError::CacheIntegrityFailure)
        );
        server.join().unwrap();
        assert!(!root.path().join(&digest).exists());
        assert_eq!(std::fs::read_dir(root.path()).unwrap().count(), 0);
        std::fs::write(root.path().join(&digest), data).unwrap();
        assert_eq!(
            download_with_client(
                &client(),
                "http://127.0.0.1:1/",
                root.path(),
                &digest,
                data.len() as u64
            ),
            Err(CacheError::CacheIntegrityFailure)
        );
        assert_eq!(std::fs::read(root.path().join(&digest)).unwrap(), data);
    }
    #[test]
    fn interrupted_download_does_not_publish_or_leave_temporary_file() {
        let root = tempfile::tempdir().unwrap();
        let data = b"complete payload";
        let digest = sha(data);
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let server = thread::spawn(move || {
            let (mut socket, _) = listener.accept().unwrap();
            socket
                .set_read_timeout(Some(Duration::from_secs(3)))
                .unwrap();
            let mut request = Vec::new();
            let mut buf = [0; 256];
            while !request.ends_with(b"\r\n\r\n") {
                let n = socket.read(&mut buf).unwrap();
                assert!(n > 0);
                request.extend_from_slice(&buf[..n]);
            }
            write!(
                socket,
                "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\nshort",
                data.len()
            )
            .unwrap();
        });
        let result = download_with_client(
            &client(),
            &format!("http://{address}/file"),
            root.path(),
            &digest,
            data.len() as u64,
        );
        server.join().unwrap();
        assert!(result.is_err());
        assert!(!root.path().join(&digest).exists());
        assert_eq!(std::fs::read_dir(root.path()).unwrap().count(), 0);
    }

    #[test]
    fn final_object_is_not_visible_until_download_is_verified() {
        use std::sync::mpsc;
        let root = tempfile::tempdir().unwrap();
        let root_path = root.path().to_owned();
        let data = b"synthetic payload";
        let digest = sha(data);
        let expected = digest.clone();
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let (sent_tx, sent_rx) = mpsc::channel();
        let (resume_tx, resume_rx) = mpsc::channel();
        let server = thread::spawn(move || {
            let (mut socket, _) = listener.accept().unwrap();
            socket
                .set_read_timeout(Some(Duration::from_secs(3)))
                .unwrap();
            let mut request = Vec::new();
            let mut buf = [0; 256];
            while !request.ends_with(b"\r\n\r\n") {
                let n = socket.read(&mut buf).unwrap();
                assert!(n > 0);
                request.extend_from_slice(&buf[..n]);
            }
            write!(
                socket,
                "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                data.len()
            )
            .unwrap();
            socket.write_all(&data[..4]).unwrap();
            sent_tx.send(()).unwrap();
            resume_rx.recv_timeout(Duration::from_secs(3)).unwrap();
            socket.write_all(&data[4..]).unwrap();
        });
        let downloader = thread::spawn(move || {
            download_with_client(
                &client(),
                &format!("http://{address}/file"),
                &root_path,
                &expected,
                data.len() as u64,
            )
        });
        sent_rx.recv_timeout(Duration::from_secs(3)).unwrap();
        let visible_before_completion = root.path().join(&digest).exists();
        resume_tx.send(()).unwrap();
        server.join().unwrap();
        let result = downloader.join().unwrap().unwrap();
        assert!(!visible_before_completion);
        assert_eq!(std::fs::read(result).unwrap(), data);
    }

    #[test]
    fn rejects_untrusted_names_and_hashes() {
        for name in ["../x", "a/b", "https://x", "x%2f", "x?y", ""] {
            assert_eq!(validate_name(name), Err(CacheError::CacheInvalidInput));
        }
        assert_eq!(
            validate_digest("invalid"),
            Err(CacheError::CacheInvalidInput)
        );
        assert_eq!(
            digest_reader(&b"abc"[..], std::io::sink(), 2),
            Err(CacheError::CacheTooLarge)
        );
    }
}
