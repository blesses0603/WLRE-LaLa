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
pub struct DownloadRequest<'a> {
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

pub fn download_selected(request: &DownloadRequest<'_>) -> Result<Vec<PathBuf>, DownloadError> {
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
