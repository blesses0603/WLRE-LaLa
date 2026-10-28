//! 以可信 SHA-256 綁定增量預覽與有限額的快取下載。
use crate::{bundle_index::BundleIndex, update_plan, verified_cache, version_map::Platform};
use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
};
pub use wlre_core_observability::ErrorCode as DownloadError;

/// 對每個預覽封包提供來自可信來源的 SHA-256；官方 MD5/CRC 不能直接充當。
/// 必須使用私有可信目錄。全部檢查通過後才逐個下載；已通過校驗的快取物件直接重用。
/// 額度上限保守計入全部選定物件，包括可能的快取命中。失敗時已完成物件保留。
/// 本函式不執行版本啟用、提取、回滾或排程，也不保證已確認最新狀態。
struct DownloadRequest<'a> {
    pub root: &'a Path,
    pub platform: Platform,
    pub data_version: &'a str,
    pub current: &'a BundleIndex,
    pub previous: Option<&'a BundleIndex>,
    pub requested: &'a [String],
    pub trusted: &'a BTreeMap<String, String>,
    pub max_files: usize,
    pub max_bytes: u64,
}

fn download_selected(request: &DownloadRequest<'_>) -> Result<Vec<PathBuf>, DownloadError> {
    let plan = update_plan::plan(request.current, request.previous, request.requested)?;
    run_plan(
        &plan,
        request.trusted,
        request.max_files,
        request.max_bytes,
        |item, digest| {
            verified_cache::download_observed_bundle(
                request.root,
                request.platform,
                request.data_version,
                &item.name,
                digest,
                item.size,
            )
        },
    )
}

/// 單一封包的已解壓容器項目；遊戲物件格式尚未解析。
#[derive(Debug)]
pub struct ExtractedBundle {
    pub name: String,
    pub entries: Vec<crate::unity_container::Entry>,
}

/// 下載及驗證所有選定封包，並於記憶體提取 UnityFS 項目。
/// 全部提取結果上限 128 MiB；回傳資料須保持私有。
/// 需可信 SHA-256、私有目錄；不支援加密封包或 TextAsset 解析。
fn download_and_extract(
    request: &DownloadRequest<'_>,
) -> Result<Vec<ExtractedBundle>, DownloadError> {
    let plan = update_plan::plan(request.current, request.previous, request.requested)?;
    let paths = download_selected(request)?;
    let mut extracted = Vec::with_capacity(plan.len());
    let mut total = 0usize;
    for (item, path) in plan.iter().zip(paths) {
        let sha = request
            .trusted
            .get(&item.name)
            .ok_or(DownloadError::TrustedDigestMissing)?;
        use std::io::Read;
        let file = std::fs::File::open(path).map_err(|_| DownloadError::StorageFailure)?;
        let mut bytes = Vec::new();
        file.take(64 * 1024 * 1024 + 1)
            .read_to_end(&mut bytes)
            .map_err(|_| DownloadError::StorageFailure)?;
        let entries = crate::unity_container::extract(&bytes, sha)?;
        for entry in &entries {
            total = total
                .checked_add(entry.data.len())
                .ok_or(DownloadError::ExtractionLimitExceeded)?;
            if total > 128 * 1024 * 1024 {
                return Err(DownloadError::ExtractionLimitExceeded);
            }
        }
        extracted.push(ExtractedBundle {
            name: item.name.clone(),
            entries,
        });
    }
    Ok(extracted)
}

/// 依官方版本對照取得最新觀察的兩份清單，下載及提取後再次查詢確認未變動。
/// 摘要需由呼叫端以可信方式提供；不保存或切換版本狀態，也不啟用舊版本。
/// 只支援已觀察的平台與資料版本；版本未知、來源失敗或期間變更即回報錯誤。
pub struct LatestRequest<'a> {
    pub root: &'a Path,
    pub platform: Platform,
    pub executable: &'a str,
    pub package: crate::bundle_index::Package,
    pub requested: &'a [String],
    pub trusted: &'a BTreeMap<String, String>,
    pub max_files: usize,
    pub max_bytes: u64,
}

pub fn download_latest(request: &LatestRequest<'_>) -> Result<Vec<ExtractedBundle>, DownloadError> {
    let first = crate::manifest_snapshot::fetch(request.platform, request.executable)?;
    let current = match request.package {
        crate::bundle_index::Package::Data => &first.data,
        crate::bundle_index::Package::Main => &first.main,
    };
    let selected = DownloadRequest {
        root: request.root,
        platform: request.platform,
        data_version: &first.data_version,
        current,
        previous: None,
        requested: request.requested,
        trusted: request.trusted,
        max_files: request.max_files,
        max_bytes: request.max_bytes,
    };
    let result = download_and_extract(&selected)?;
    let latest = crate::manifest_snapshot::fetch(request.platform, request.executable)?;
    confirm_same_observation(&first, &latest)?;
    Ok(result)
}

fn confirm_same_observation(
    first: &crate::manifest_snapshot::Snapshot,
    latest: &crate::manifest_snapshot::Snapshot,
) -> Result<(), DownloadError> {
    if first.data_version != latest.data_version
        || first.data_sha256 != latest.data_sha256
        || first.main_sha256 != latest.main_sha256
    {
        return Err(DownloadError::SnapshotChanged);
    }
    Ok(())
}

fn run_plan<F>(
    plan: &[update_plan::PlannedBundle],
    trusted: &BTreeMap<String, String>,
    max_files: usize,
    max_bytes: u64,
    mut download: F,
) -> Result<Vec<PathBuf>, DownloadError>
where
    F: FnMut(&update_plan::PlannedBundle, &str) -> Result<PathBuf, DownloadError>,
{
    if plan.len() > max_files {
        return Err(DownloadError::DownloadQuotaExceeded);
    }
    let mut total = 0u64;
    for item in plan {
        verified_cache::validate_name(&item.name)?;
        let value = trusted
            .get(&item.name)
            .ok_or(DownloadError::TrustedDigestMissing)?;
        verified_cache::validate_digest(value)?;
        if item.size > 64 * 1024 * 1024 {
            return Err(DownloadError::CacheTooLarge);
        }
        total = total
            .checked_add(item.size)
            .ok_or(DownloadError::DownloadQuotaExceeded)?;
        if total > max_bytes {
            return Err(DownloadError::DownloadQuotaExceeded);
        }
    }
    let mut paths = Vec::with_capacity(plan.len());
    for item in plan {
        paths.push(download(item, &trusted[&item.name])?);
    }
    Ok(paths)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::update_plan::{Change, PlannedBundle};
    fn item(name: &str, size: u64) -> PlannedBundle {
        PlannedBundle {
            name: name.into(),
            size,
            change: Change::Changed,
        }
    }
    #[test]
    fn failed_extraction_does_not_return_partial_data() {
        use crate::bundle_index::Bundle;
        use sha2::{Digest, Sha256};
        let root = tempfile::tempdir().unwrap();
        let data = b"not unity";
        let digest = format!("{:x}", Sha256::digest(data));
        std::fs::write(root.path().join(&digest), data).unwrap();
        let index = BundleIndex {
            file_version: "2.2.5".into(),
            package_name: "DataPackage".into(),
            package_version: "v".into(),
            asset_list: vec![],
            bundle_list: vec![Bundle {
                bundle_name: "sample.bundle".into(),
                unity_crc: 0,
                file_hash: "x".into(),
                file_crc: "x".into(),
                file_size: data.len() as u64,
                encrypted: false,
                tags: vec![],
                depend_ids: vec![],
            }],
        };
        let selected = vec!["sample.bundle".to_owned()];
        let pins = BTreeMap::from([("sample.bundle".to_owned(), digest)]);
        let request = DownloadRequest {
            root: root.path(),
            platform: Platform::Windows,
            data_version: "1.3.21",
            current: &index,
            previous: None,
            requested: &selected,
            trusted: &pins,
            max_files: 1,
            max_bytes: 100,
        };
        assert!(matches!(
            download_and_extract(&request),
            Err(DownloadError::ExtractionInvalid)
        ));
    }

    #[test]
    fn refuses_changed_observation_even_if_version_number_is_same() {
        use crate::manifest_snapshot::Snapshot;
        fn index(name: &str) -> BundleIndex {
            BundleIndex {
                file_version: "2.2.5".into(),
                package_name: name.into(),
                package_version: "revision".into(),
                asset_list: vec![],
                bundle_list: vec![],
            }
        }
        let make = |data: &str, main: &str| Snapshot {
            data_version: "1.3.21".into(),
            data_sha256: data.into(),
            main_sha256: main.into(),
            data: index("DataPackage"),
            main: index("MainPackage"),
        };
        assert_eq!(
            confirm_same_observation(&make("a", "b"), &make("a", "b")),
            Ok(())
        );
        assert_eq!(
            confirm_same_observation(&make("a", "b"), &make("changed", "b")),
            Err(DownloadError::SnapshotChanged)
        );
        assert_eq!(
            confirm_same_observation(&make("a", "b"), &make("a", "changed")),
            Err(DownloadError::SnapshotChanged)
        );
    }

    #[test]
    fn validates_all_inputs_before_any_download() {
        let plan = vec![item("a.bundle", 3), item("b.bundle", 4)];
        let mut pins = BTreeMap::new();
        pins.insert("a.bundle".into(), "a".repeat(64));
        let mut calls = 0;
        assert_eq!(
            run_plan(&plan, &pins, 2, 10, |_, _| {
                calls += 1;
                Ok(PathBuf::new())
            }),
            Err(DownloadError::TrustedDigestMissing)
        );
        assert_eq!(calls, 0);
        pins.insert("b.bundle".into(), "b".repeat(64));
        assert_eq!(
            run_plan(&plan, &pins, 2, 6, |_, _| {
                calls += 1;
                Ok(PathBuf::new())
            }),
            Err(DownloadError::DownloadQuotaExceeded)
        );
        assert_eq!(calls, 0);
        let result = run_plan(&plan, &pins, 2, 7, |entry, _| {
            calls += 1;
            Ok(PathBuf::from(&entry.name))
        })
        .unwrap();
        assert_eq!(calls, 2);
        assert_eq!(
            result,
            vec![PathBuf::from("a.bundle"), PathBuf::from("b.bundle")]
        );
    }
    #[test]
    fn stops_at_first_failed_download() {
        let plan = vec![item("a.bundle", 1), item("b.bundle", 1)];
        let pins = BTreeMap::from([
            ("a.bundle".into(), "a".repeat(64)),
            ("b.bundle".into(), "b".repeat(64)),
        ]);
        let mut calls = 0;
        assert_eq!(
            run_plan(&plan, &pins, 2, 2, |_, _| {
                calls += 1;
                Err(DownloadError::RequestFailed)
            }),
            Err(DownloadError::RequestFailed)
        );
        assert_eq!(calls, 1);
    }
}
