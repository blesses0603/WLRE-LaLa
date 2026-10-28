//! 僅保存 LaLa 實際使用且已驗證的官方資源，不要求下載完整資源庫。
use crate::{
    bundle_index::{self, BundleIndex},
    manifest_snapshot::Snapshot,
    official_cache, version_map,
};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::{Read, Write},
    path::Path,
};
pub use wlre_core_observability::ErrorCode as OfflineError;

const CACHE_FILE: &str = "last-verified-snapshot.json";
const MAX_INDEX_BYTES: u64 = 64 * 1024 * 1024;
const SCHEMA_VERSION: u8 = 3;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Stored {
    schema_version: u8,
    snapshot: Snapshot,
    /// 只記錄真正因功能而下載／驗證的封包名稱，不能宣稱其餘素材已取得。
    selected_names: Vec<String>,
    /// 每個已選封包最後一次成功更新時的本機 SHA-256；不是官方簽章。
    bundle_sha256: BTreeMap<String, String>,
}

/// 已使用本機官方 MD5／CRC32 資料檢查所有封包；不包含來源簽章保證。
#[derive(Debug, Eq, PartialEq)]
pub struct OfflineStatus {
    pub data_version: String,
    pub bundle_count: usize,
}

/// 舊有完整清單驗證入口；只供確實需要全部封包的呼叫端使用。
/// LaLa 應優先使用 save_selected，避免要求整包下載。
pub fn save(root: &Path, snapshot: &Snapshot) -> Result<(), OfflineError> {
    let all = snapshot
        .data
        .bundle_list
        .iter()
        .chain(snapshot.main.bundle_list.iter())
        .collect::<Vec<_>>();
    save_selected(root, snapshot, &all)
}

/// 保存本輪 LaLa 功能實際使用的官方封包；同一官方快照下合併先前使用的封包。
/// 所有選定檔案必須先完成本機檢驗，失敗不覆蓋原本的快照。
pub fn save_selected(
    root: &Path,
    snapshot: &Snapshot,
    selected: &[&crate::bundle_index::Bundle],
) -> Result<(), OfflineError> {
    check_root(root)?;
    validate_snapshot(snapshot)?;
    let mut names: BTreeSet<String> = selected
        .iter()
        .map(|bundle| bundle.bundle_name.to_ascii_lowercase())
        .collect();
    if names.is_empty() {
        return Err(OfflineError::ResourceNotFound);
    }
    if let Some(previous) = read_stored(root)? {
        if previous.snapshot.data_version == snapshot.data_version
            && previous.snapshot.announced_executable == snapshot.announced_executable
            && previous.snapshot.data_sha256 == snapshot.data_sha256
            && previous.snapshot.main_sha256 == snapshot.main_sha256
        {
            names.extend(previous.selected_names);
        }
    }
    let bundle_sha256 = verified_digests(root, snapshot, &names)?;
    let data = serde_json::to_vec(&Stored {
        schema_version: SCHEMA_VERSION,
        snapshot: snapshot.clone(),
        selected_names: names.into_iter().collect(),
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

/// 離線只檢查最近一次成功選擇的封包；不推定官方目前版本或其餘素材。
pub fn verify(root: &Path) -> Result<Option<OfflineStatus>, OfflineError> {
    let stored = match read_stored(root)? {
        Some(stored) => stored,
        None => return Ok(None),
    };
    let names: BTreeSet<_> = stored.selected_names.iter().cloned().collect();
    if names.len() != stored.selected_names.len() || names.is_empty() {
        return Err(OfflineError::IndexInvalidEntry);
    }
    let actual = verified_digests(root, &stored.snapshot, &names)?;
    if stored.bundle_sha256 != actual {
        return Err(OfflineError::CacheIntegrityFailure);
    }
    Ok(Some(OfflineStatus {
        data_version: stored.snapshot.data_version,
        bundle_count: actual.len(),
    }))
}

fn read_stored(root: &Path) -> Result<Option<Stored>, OfflineError> {
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
    Ok(Some(stored))
}

fn verified_digests(
    root: &Path,
    snapshot: &Snapshot,
    names: &BTreeSet<String>,
) -> Result<BTreeMap<String, String>, OfflineError> {
    let mut seen: BTreeMap<String, (&crate::bundle_index::Bundle, String)> = BTreeMap::new();
    for index in [&snapshot.data, &snapshot.main] {
        for bundle in &index.bundle_list {
            let key = bundle.bundle_name.to_ascii_lowercase();
            if !names.contains(&key) {
                continue;
            }
            if bundle.encrypted {
                return Err(OfflineError::UnsupportedEncryption);
            }
            if let Some((previous, _)) = seen.get(&key) {
                if !previous.file_hash.eq_ignore_ascii_case(&bundle.file_hash)
                    || !previous.file_crc.eq_ignore_ascii_case(&bundle.file_crc)
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
    if names.len() != seen.len() {
        return Err(OfflineError::ResourceNotFound);
    }
    Ok(seen
        .into_iter()
        .map(|(name, (_, sha))| (name, sha))
        .collect())
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
    fn replaces_last_verified_snapshot_with_newer_observation() {
        let dir = tempfile::tempdir().unwrap();
        let old = snapshot();
        write_bundle(dir.path(), &old.data.bundle_list[0], b"offline test");
        write_bundle(dir.path(), &old.main.bundle_list[0], b"offline main");
        save(dir.path(), &old).unwrap();
        let mut next = snapshot();
        next.data_version = "1.3.22".into();
        save(dir.path(), &next).unwrap();
        assert_eq!(
            verify(dir.path()).unwrap(),
            Some(OfflineStatus {
                data_version: "1.3.22".into(),
                bundle_count: 2,
            })
        );
    }

    #[test]
    fn failed_new_snapshot_does_not_destroy_last_verified_cache() {
        let dir = tempfile::tempdir().unwrap();
        let old = snapshot();
        write_bundle(dir.path(), &old.data.bundle_list[0], b"offline test");
        write_bundle(dir.path(), &old.main.bundle_list[0], b"offline main");
        save(dir.path(), &old).unwrap();
        let mut next = snapshot();
        next.data_version = "1.3.22".into();
        next.data.bundle_list[0].file_hash = "0".repeat(32);
        assert_eq!(
            save(dir.path(), &next),
            Err(OfflineError::CacheIntegrityFailure)
        );
        assert_eq!(
            verify(dir.path()).unwrap(),
            Some(OfflineStatus {
                data_version: "1.3.21".into(),
                bundle_count: 2,
            })
        );
    }

    #[test]
    fn saves_only_selected_bundles_and_merges_another_feature() {
        let dir = tempfile::tempdir().unwrap();
        let value = snapshot();
        let data = &value.data.bundle_list[0];
        let main = &value.main.bundle_list[0];
        write_bundle(dir.path(), data, b"offline test");
        save_selected(dir.path(), &value, &[data]).unwrap();
        assert_eq!(
            verify(dir.path()).unwrap(),
            Some(OfflineStatus {
                data_version: "1.3.21".into(),
                bundle_count: 1,
            })
        );
        write_bundle(dir.path(), main, b"offline main");
        save_selected(dir.path(), &value, &[main]).unwrap();
        assert_eq!(
            verify(dir.path()).unwrap(),
            Some(OfflineStatus {
                data_version: "1.3.21".into(),
                bundle_count: 2,
            })
        );
    }

    #[test]
    fn newer_version_does_not_require_unrequested_older_assets() {
        let dir = tempfile::tempdir().unwrap();
        let old = snapshot();
        write_bundle(dir.path(), &old.data.bundle_list[0], b"offline test");
        save_selected(dir.path(), &old, &[&old.data.bundle_list[0]]).unwrap();
        let mut next = snapshot();
        next.data_version = "1.3.22".into();
        write_bundle(dir.path(), &next.main.bundle_list[0], b"offline main");
        save_selected(dir.path(), &next, &[&next.main.bundle_list[0]]).unwrap();
        assert_eq!(
            verify(dir.path()).unwrap(),
            Some(OfflineStatus {
                data_version: "1.3.22".into(),
                bundle_count: 1,
            })
        );
    }

    #[test]
    fn refuses_symlinked_metadata() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join(CACHE_FILE);
        std::fs::create_dir(&path).unwrap();
        assert_eq!(verify(dir.path()), Err(OfflineError::CacheInvalidInput));
    }
}
