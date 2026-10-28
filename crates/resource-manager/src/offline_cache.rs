//! 保存最近一次完整下載驗證的官方索引；離線僅能辨識「上次已驗證」，不代表最新版本。
use crate::{
    bundle_index::{self, BundleIndex},
    manifest_snapshot::Snapshot,
    official_cache, version_map,
};
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    fs,
    io::{Read, Write},
    path::Path,
};
pub use wlre_core_observability::ErrorCode as OfflineError;

const CACHE_FILE: &str = "last-verified-snapshot.json";
const MAX_INDEX_BYTES: u64 = 64 * 1024 * 1024;
const SCHEMA_VERSION: u8 = 2;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Stored {
    schema_version: u8,
    snapshot: Snapshot,
    /// 每個封包在最後一次成功更新時的本機 SHA-256；不是官方簽章。
    bundle_sha256: BTreeMap<String, String>,
}

/// 已使用本機官方 MD5／CRC32 資料檢查所有封包；不包含來源簽章保證。
#[derive(Debug, Eq, PartialEq)]
pub struct OfflineStatus {
    pub data_version: String,
    pub bundle_count: usize,
}

/// 下載及兩次官方快照一致性確認通過後，才呼叫此函式。
/// 快取根目錄須私有且只有一個寫入者；暫存檔與快取不放入 Git。
pub fn save(root: &Path, snapshot: &Snapshot) -> Result<(), OfflineError> {
    check_root(root)?;
    validate_snapshot(snapshot)?;
    let bundle_sha256 = verified_digests(root, snapshot)?;
    let data = serde_json::to_vec(&Stored {
        schema_version: SCHEMA_VERSION,
        snapshot: snapshot.clone(),
        bundle_sha256,
    })
    .map_err(|_| OfflineError::StorageFailure)?;
    if data.len() as u64 > MAX_INDEX_BYTES {
        return Err(OfflineError::IndexTooLarge);
    }
    let mut temp =
        tempfile::NamedTempFile::new_in(root).map_err(|_| OfflineError::StorageFailure)?;
    temp.write_all(&data)
        .map_err(|_| OfflineError::StorageFailure)?;
    temp.as_file_mut()
        .sync_all()
        .map_err(|_| OfflineError::StorageFailure)?;
    temp.persist(root.join(CACHE_FILE))
        .map_err(|_| OfflineError::StorageFailure)?;
    #[cfg(unix)]
    fs::File::open(root)
        .and_then(|dir| dir.sync_all())
        .map_err(|_| OfflineError::StorageFailure)?;
    Ok(())
}

/// 脫機時檢查上一次成功清單的每個封包是否仍存在且符合大小與官方 MD5／CRC32。
/// 清單是本機快取而非簽章，回傳值不得顯示成「已是官方最新版」。
pub fn verify(root: &Path) -> Result<Option<OfflineStatus>, OfflineError> {
    check_root(root)?;
    let path = root.join(CACHE_FILE);
    let meta = match fs::symlink_metadata(&path) {
        Ok(meta) => meta,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(_) => return Err(OfflineError::StorageFailure),
    };
    if !meta.file_type().is_file() {
        return Err(OfflineError::CacheInvalidInput);
    }
    if meta.len() > MAX_INDEX_BYTES {
        return Err(OfflineError::IndexTooLarge);
    }
    let mut data = Vec::new();
    fs::File::open(&path)
        .map_err(|_| OfflineError::StorageFailure)?
        .take(MAX_INDEX_BYTES + 1)
        .read_to_end(&mut data)
        .map_err(|_| OfflineError::StorageFailure)?;
    if data.len() as u64 > MAX_INDEX_BYTES {
        return Err(OfflineError::IndexTooLarge);
    }
    let stored: Stored =
        serde_json::from_slice(&data).map_err(|_| OfflineError::IndexInvalidEntry)?;
    if stored.schema_version != SCHEMA_VERSION {
        return Err(OfflineError::IndexUnsupportedVersion);
    }
    validate_snapshot(&stored.snapshot)?;
    let actual = verified_digests(root, &stored.snapshot)?;
    if stored.bundle_sha256 != actual {
        return Err(OfflineError::CacheIntegrityFailure);
    }
    Ok(Some(OfflineStatus {
        data_version: stored.snapshot.data_version,
        bundle_count: actual.len(),
    }))
}


fn verified_digests(
    root: &Path,
    snapshot: &Snapshot,
) -> Result<BTreeMap<String, String>, OfflineError> {
    let mut seen: BTreeMap<String, (&crate::bundle_index::Bundle, String)> = BTreeMap::new();
    for index in [&snapshot.data, &snapshot.main] {
        for bundle in &index.bundle_list {
            if bundle.encrypted {
                return Err(OfflineError::UnsupportedEncryption);
            }
            let key = bundle.bundle_name.to_ascii_lowercase();
            if let Some((previous, _)) = seen.get(&key) {
                if previous.file_hash != bundle.file_hash
                    || previous.file_crc != bundle.file_crc
                    || previous.file_size != bundle.file_size
                {
                    return Err(OfflineError::IndexDuplicatePath);
                }
                continue;
            }
            let digest = official_cache::cached_sha256(root, bundle)?
                .ok_or(OfflineError::CacheIntegrityFailure)?;
            seen.insert(key, (bundle, digest));
        }
    }
    Ok(seen.into_iter().map(|(name, (_, sha))| (name, sha)).collect())
}

fn check_root(root: &Path) -> Result<(), OfflineError> {
    let metadata = fs::symlink_metadata(root).map_err(|_| OfflineError::StorageFailure)?;
    if !metadata.file_type().is_dir() {
        return Err(OfflineError::CacheInvalidInput);
    }
    Ok(())
}

fn validate_snapshot(snapshot: &Snapshot) -> Result<(), OfflineError> {
    if !version_map::valid_version(&snapshot.data_version)
        || !version_map::valid_version(&snapshot.announced_executable)
        || snapshot.data.package_name != "DataPackage"
        || snapshot.main.package_name != "MainPackage"
    {
        return Err(OfflineError::IndexInvalidEntry);
    }
    for sha in [&snapshot.data_sha256, &snapshot.main_sha256] {
        if sha.len() != 64 || !sha.bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err(OfflineError::IndexInvalidEntry);
        }
    }
    // 保持二進位清單解析器使用的相同邊界與參照規則。
    fn check(index: &BundleIndex) -> Result<(), OfflineError> {
        let json = serde_json::to_vec(index).map_err(|_| OfflineError::IndexInvalidEntry)?;
        bundle_index::parse(&json).map(|_| ())
    }
    check(&snapshot.data)?;
    check(&snapshot.main)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::bundle_index::{Bundle, BundleIndex};
    use md5::{Digest, Md5};

    fn snapshot() -> Snapshot {
        fn bundle(name: &str, bytes: &[u8]) -> Bundle {
            Bundle {
                bundle_name: name.into(),
                unity_crc: 0,
                file_hash: format!("{:x}", Md5::digest(bytes)),
                file_crc: crc32fast::hash(bytes)
                    .to_le_bytes()
                    .iter()
                    .map(|byte| format!("{byte:02x}"))
                    .collect(),
                file_size: bytes.len() as u64,
                encrypted: false,
                tags: vec![],
                depend_ids: vec![],
            }
        }
        let index = |name: &str, bundles: Vec<Bundle>| BundleIndex {
            file_version: "2.2.5".into(),
            package_name: name.into(),
            package_version: "1".into(),
            asset_list: vec![],
            bundle_list: bundles,
        };
        Snapshot {
            data_version: "1.3.21".into(),
            announced_executable: "1.3.0".into(),
            data_sha256: "a".repeat(64),
            main_sha256: "b".repeat(64),
            data: index("DataPackage", vec![bundle("data.bundle", b"offline test")]),
            main: index("MainPackage", vec![bundle("main.bundle", b"offline main")]),
        }
    }

    fn write_bundle(root: &Path, bundle: &Bundle, bytes: &[u8]) {
        std::fs::write(
            root.join(format!(
                "official-{}-{}-{}",
                bundle.file_hash, bundle.file_crc, bundle.file_size
            )),
            bytes,
        )
        .unwrap();
    }

    #[test]
    fn missing_snapshot_is_not_latest_or_verified() {
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(verify(dir.path()).unwrap(), None);
    }

    #[test]
    fn verifies_saved_snapshot_offline_without_network() {
        let dir = tempfile::tempdir().unwrap();
        let value = snapshot();
        write_bundle(dir.path(), &value.data.bundle_list[0], b"offline test");
        write_bundle(dir.path(), &value.main.bundle_list[0], b"offline main");
        save(dir.path(), &value).unwrap();
        assert_eq!(
            verify(dir.path()).unwrap(),
            Some(OfflineStatus {
                data_version: "1.3.21".into(),
                bundle_count: 2,
            })
        );
    }

    #[test]
    fn missing_or_corrupted_bundle_is_not_reported_as_offline_ready() {
        let dir = tempfile::tempdir().unwrap();
        let value = snapshot();
        assert_eq!(
            save(dir.path(), &value),
            Err(OfflineError::CacheIntegrityFailure)
        );
        write_bundle(dir.path(), &value.data.bundle_list[0], b"offline test");
        write_bundle(dir.path(), &value.main.bundle_list[0], b"offline main");
        save(dir.path(), &value).unwrap();
        write_bundle(dir.path(), &value.main.bundle_list[0], b"offline bad!");
        assert_eq!(verify(dir.path()), Err(OfflineError::CacheIntegrityFailure));
    }

    #[test]
    fn corrupted_metadata_is_rejected_without_network() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join(CACHE_FILE), b"broken").unwrap();
        assert_eq!(verify(dir.path()), Err(OfflineError::IndexInvalidEntry));
    }

    #[test]
    fn refuses_symlinked_metadata() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join(CACHE_FILE);
        std::fs::create_dir(&path).unwrap();
        assert_eq!(verify(dir.path()), Err(OfflineError::CacheInvalidInput));
    }
}
