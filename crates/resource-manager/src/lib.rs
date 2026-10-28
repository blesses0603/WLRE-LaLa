//! 與官方格式無關的資源管理基礎。

use std::collections::BTreeMap;

pub mod binary_manifest;
pub mod bundle_index;
pub mod manifest_snapshot;
pub mod official_probe;
pub mod script_index;
pub mod update_download;
pub mod update_plan;
pub mod verified_cache;
pub mod version_map;
pub use wlre_core_observability::ErrorCode as ResourceError;

/// 可攜式資源相對路徑；不代表檔案系統操作已防止符號連結逃逸。
#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct ResourcePath(String);

impl ResourcePath {
    pub fn new(value: &str) -> Result<Self, ResourceError> {
        if value.is_empty()
            || value.split('/').any(|part| {
                part.is_empty()
                    || part == "."
                    || part == ".."
                    || part
                        .chars()
                        .any(|c| c.is_control() || "\\:*?\"<>|".contains(c))
            })
        {
            return Err(ResourceError::InvalidPath);
        }
        Ok(Self(value.to_owned()))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

/// 識別值的來源與可信度由呼叫端負責，不等同完整性校驗。
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ResourceEntry {
    pub path: ResourcePath,
    pub revision: String,
}

/// 平台適配器需自行實作安全存取與錯誤復原。
pub trait ResourceStorage {
    fn read(&self, path: &ResourcePath) -> Result<Option<Vec<u8>>, ResourceError>;
}

#[derive(Debug, Eq, PartialEq)]
pub struct UpdatePlan {
    pub added: Vec<ResourcePath>,
    pub changed: Vec<ResourcePath>,
}

/// 比較呼叫端提供的快照；不推斷官方版本，也不刪除本機檔案。
pub fn plan_update(
    current: &[ResourceEntry],
    remote: &[ResourceEntry],
) -> Result<UpdatePlan, ResourceError> {
    fn index(entries: &[ResourceEntry]) -> Result<BTreeMap<&ResourcePath, &str>, ResourceError> {
        let mut result = BTreeMap::new();
        for entry in entries {
            if result
                .insert(&entry.path, entry.revision.as_str())
                .is_some()
            {
                return Err(ResourceError::DuplicatePath);
            }
        }
        Ok(result)
    }
    let current = index(current)?;
    let remote = index(remote)?;
    let mut plan = UpdatePlan {
        added: Vec::new(),
        changed: Vec::new(),
    };
    for (path, revision) in remote {
        match current.get(path) {
            None => plan.added.push(path.clone()),
            Some(old) if *old != revision => plan.changed.push(path.clone()),
            Some(_) => {}
        }
    }
    Ok(plan)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entry(path: &str, revision: &str) -> ResourceEntry {
        ResourceEntry {
            path: ResourcePath::new(path).unwrap(),
            revision: revision.into(),
        }
    }

    #[test]
    fn rejects_unsafe_paths() {
        for path in [
            "", "/a", "../a", "a/../b", "a//b", "C:/a", "a\\b", "a/.", "a\0b",
        ] {
            assert_eq!(ResourcePath::new(path), Err(ResourceError::InvalidPath));
        }
        assert_eq!(
            ResourcePath::new("目錄/file.dat").unwrap().as_str(),
            "目錄/file.dat"
        );
    }

    #[test]
    fn compares_snapshots_without_deleting() {
        let current = [
            entry("same", "1"),
            entry("changed", "1"),
            entry("removed", "1"),
        ];
        let remote = [entry("same", "1"), entry("changed", "2"), entry("new", "1")];
        let plan = plan_update(&current, &remote).unwrap();
        assert_eq!(plan.added, vec![ResourcePath::new("new").unwrap()]);
        assert_eq!(plan.changed, vec![ResourcePath::new("changed").unwrap()]);
    }

    #[test]
    fn rejects_duplicate_entries_in_either_snapshot() {
        let duplicates = [entry("a", "1"), entry("a", "2")];
        assert_eq!(
            plan_update(&duplicates, &[]),
            Err(ResourceError::DuplicatePath)
        );
        assert_eq!(
            plan_update(&[], &duplicates),
            Err(ResourceError::DuplicatePath)
        );
    }
}
