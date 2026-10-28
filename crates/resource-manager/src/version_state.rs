//! 可信私有快取中的版本切換與上一版本回復。
use crate::verified_cache;
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeSet,
    io::{Read, Write},
    path::Path,
};
pub use wlre_core_observability::ErrorCode as StateError;
const STATE_FILE: &str = "active-versions.json";
const MAX_STATE_BYTES: u64 = 4 * 1024 * 1024;
const MAX_OBJECTS: usize = 20_000;
const MAX_OBJECT_SIZE: u64 = 64 * 1024 * 1024;

#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CacheObject {
    pub sha256: String,
    pub size: u64,
}
/// 身分由呼叫端依可信清單計算的 SHA-256 指定。
#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Version {
    pub identity: String,
    pub objects: Vec<CacheObject>,
}
#[derive(Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct State {
    pub schema_version: u8,
    pub current: Version,
    pub previous: Option<Version>,
}

fn validate(root: &Path, version: &Version) -> Result<(), StateError> {
    let id = verified_cache::validate_digest(&version.identity)?;
    if id != version.identity || version.objects.is_empty() || version.objects.len() > MAX_OBJECTS {
        return Err(StateError::VersionStateInvalid);
    }
    let mut seen = BTreeSet::new();
    for object in &version.objects {
        let digest = verified_cache::validate_digest(&object.sha256)?;
        if digest != object.sha256 || object.size > MAX_OBJECT_SIZE || !seen.insert(&object.sha256)
        {
            return Err(StateError::VersionStateInvalid);
        }
        if !verified_cache::verify_existing(&root.join(digest), &object.sha256, object.size)? {
            return Err(StateError::CacheIntegrityFailure);
        }
    }
    Ok(())
}
fn root_check(root: &Path) -> Result<(), StateError> {
    let metadata = std::fs::symlink_metadata(root).map_err(|_| StateError::StorageFailure)?;
    if !metadata.file_type().is_dir() {
        return Err(StateError::CacheInvalidInput);
    }
    Ok(())
}
/// 讀取狀態並重新驗證當前物件；孤立暫存檔不會變成已啟用版本。
/// 根目錄及祖先須私有可信；呼叫端必須保證整個讀取與更新期間只有一個寫入者。
pub fn read(root: &Path) -> Result<Option<State>, StateError> {
    root_check(root)?;
    let path = root.join(STATE_FILE);
    let metadata = match std::fs::symlink_metadata(&path) {
        Ok(m) => m,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(_) => return Err(StateError::StorageFailure),
    };
    if !metadata.file_type().is_file() || metadata.len() > MAX_STATE_BYTES {
        return Err(StateError::VersionStateInvalid);
    }
    let mut bytes = Vec::new();
    std::fs::File::open(path)
        .map_err(|_| StateError::StorageFailure)?
        .take(MAX_STATE_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| StateError::StorageFailure)?;
    if bytes.len() as u64 > MAX_STATE_BYTES {
        return Err(StateError::VersionStateInvalid);
    }
    let state: State =
        serde_json::from_slice(&bytes).map_err(|_| StateError::VersionStateInvalid)?;
    if state.schema_version != 1 {
        return Err(StateError::VersionStateInvalid);
    }
    validate(root, &state.current)?;
    Ok(Some(state))
}
fn persist(root: &Path, state: &State) -> Result<(), StateError> {
    let bytes = serde_json::to_vec(state).map_err(|_| StateError::StorageFailure)?;
    if bytes.len() as u64 > MAX_STATE_BYTES {
        return Err(StateError::VersionStateInvalid);
    }
    let mut tmp = tempfile::NamedTempFile::new_in(root).map_err(|_| StateError::StorageFailure)?;
    tmp.write_all(&bytes)
        .map_err(|_| StateError::StorageFailure)?;
    tmp.as_file()
        .sync_all()
        .map_err(|_| StateError::StorageFailure)?;
    tmp.persist(root.join(STATE_FILE))
        .map_err(|_| StateError::StorageFailure)?;
    Ok(())
}
/// 驗證全部物件後切換；失敗時保留目前狀態。只保留上一版本，不刪除快取。
/// 需由呼叫端排除並行寫入，且此函式尚未保證斷電後目錄項目的持久化。
pub fn activate(root: &Path, next: Version) -> Result<State, StateError> {
    let old = read(root)?;
    validate(root, &next)?;
    if old
        .as_ref()
        .is_some_and(|s| s.current.identity == next.identity && s.current != next)
    {
        return Err(StateError::VersionStateInvalid);
    }
    let previous = match old {
        Some(state) if state.current == next => state.previous,
        Some(state) => Some(state.current),
        None => None,
    };
    let state = State {
        schema_version: 1,
        current: next,
        previous,
    };
    persist(root, &state)?;
    Ok(state)
}
/// 驗證上一版本的全部物件後交換目前及上一版本。
pub fn rollback(root: &Path) -> Result<State, StateError> {
    let state = read(root)?.ok_or(StateError::RollbackUnavailable)?;
    let previous = state.previous.ok_or(StateError::RollbackUnavailable)?;
    validate(root, &previous)?;
    let next = State {
        schema_version: 1,
        current: previous,
        previous: Some(state.current),
    };
    persist(root, &next)?;
    Ok(next)
}

#[cfg(test)]
mod tests {
    use super::*;
    use sha2::{Digest, Sha256};
    fn version(root: &Path, data: &[u8], marker: u8) -> Version {
        let sha = format!("{:x}", Sha256::digest(data));
        std::fs::write(root.join(&sha), data).unwrap();
        Version {
            identity: format!("{marker:064x}"),
            objects: vec![CacheObject {
                sha256: sha,
                size: data.len() as u64,
            }],
        }
    }
    #[test]
    fn switches_and_rolls_back_only_after_validating_objects() {
        let root = tempfile::tempdir().unwrap();
        let a = version(root.path(), b"first", 1);
        let b = version(root.path(), b"second", 2);
        activate(root.path(), a.clone()).unwrap();
        activate(root.path(), b.clone()).unwrap();
        assert_eq!(rollback(root.path()).unwrap().current, a);
        assert_eq!(read(root.path()).unwrap().unwrap().previous, Some(b));
    }
    #[test]
    fn failed_activation_or_rollback_keeps_previous_state() {
        let root = tempfile::tempdir().unwrap();
        let a = version(root.path(), b"first", 1);
        let b = version(root.path(), b"second", 2);
        activate(root.path(), a.clone()).unwrap();
        let mut missing = b.clone();
        missing.objects[0].sha256 = "f".repeat(64);
        assert!(activate(root.path(), missing).is_err());
        assert_eq!(read(root.path()).unwrap().unwrap().current, a);
        activate(root.path(), b.clone()).unwrap();
        std::fs::write(root.path().join(&a.objects[0].sha256), b"wrong").unwrap();
        assert!(rollback(root.path()).is_err());
        assert_eq!(read(root.path()).unwrap().unwrap().current, b);
    }
    #[test]
    fn ignores_orphan_temporary_files_and_rejects_corrupt_state() {
        let root = tempfile::tempdir().unwrap();
        let a = version(root.path(), b"first", 1);
        activate(root.path(), a.clone()).unwrap();
        std::fs::write(root.path().join(".orphan"), b"partial").unwrap();
        assert_eq!(read(root.path()).unwrap().unwrap().current, a);
        std::fs::write(root.path().join(STATE_FILE), b"broken").unwrap();
        assert_eq!(read(root.path()), Err(StateError::VersionStateInvalid));
    }
}
