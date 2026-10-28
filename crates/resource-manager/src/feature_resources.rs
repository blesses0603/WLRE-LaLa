//! LaLa 功能需求與官方索引項目的精確關聯；不以檔名或目錄猜測用途。
use crate::{
    bundle_index::{Bundle, BundleIndex, Package},
    manifest_snapshot::{self, Snapshot},
    official_cache, offline_cache,
    version_map::Platform,
};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
    thread,
    time::Duration,
};
pub use wlre_core_observability::ErrorCode as FeatureError;

const REQUEST_GAP: Duration = Duration::from_millis(200);

/// LaLa 功能分類；這不是官方遊戲檔案類型。
#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd)]
pub enum Feature {
    Account,
    Character,
    Map,
    Navigation,
    Portal,
    Battle,
    Inventory,
    Storage,
    Expedition,
    Social,
    Party,
    Pet,
    Npc,
    Shop,
    Alchemy,
    Crafting,
    Dungeon,
    Cooperative,
    Maintenance,
    Analytics,
    Housing,
}

impl Feature {
    /// 穩定跨平台功能識別；僅用於功能註冊／資源需求，不代表功能或伺服器指令已可用。
    pub const ALL: [Feature; 21] = [
        Self::Account,
        Self::Character,
        Self::Map,
        Self::Navigation,
        Self::Portal,
        Self::Battle,
        Self::Inventory,
        Self::Storage,
        Self::Expedition,
        Self::Social,
        Self::Party,
        Self::Pet,
        Self::Npc,
        Self::Shop,
        Self::Alchemy,
        Self::Crafting,
        Self::Dungeon,
        Self::Cooperative,
        Self::Maintenance,
        Self::Analytics,
        Self::Housing,
    ];

    pub const fn id(self) -> &'static str {
        match self {
            Self::Account => "account",
            Self::Character => "character",
            Self::Map => "map",
            Self::Navigation => "navigation",
            Self::Portal => "portal",
            Self::Battle => "battle",
            Self::Inventory => "inventory",
            Self::Storage => "storage",
            Self::Expedition => "expedition",
            Self::Social => "social",
            Self::Party => "party",
            Self::Pet => "pet",
            Self::Npc => "npc",
            Self::Shop => "shop",
            Self::Alchemy => "alchemy",
            Self::Crafting => "crafting",
            Self::Dungeon => "dungeon",
            Self::Cooperative => "cooperative",
            Self::Maintenance => "maintenance",
            Self::Analytics => "analytics",
            Self::Housing => "housing",
        }
    }
}

/// 選擇官方二進位清單 AssetList 中的精確 Address 或 AssetPath。
/// 值必須由已驗證的官方索引和 LaLa 功能責任對照決定。
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum AssetKey {
    Address(String),
    AssetPath(String),
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AssetBinding {
    pub package: Package,
    pub key: AssetKey,
}

/// 沒有已確認對應的功能不可自動下載；允許明確宣告純通訊功能不需素材。
#[derive(Clone, Debug, Default)]
pub struct FeatureCatalog {
    entries: BTreeMap<Feature, Vec<AssetBinding>>,
}
impl FeatureCatalog {
    pub fn register_no_assets(&mut self, feature: Feature) {
        self.entries.entry(feature).or_default();
    }

    pub fn bind(&mut self, feature: Feature, binding: AssetBinding) -> Result<(), FeatureError> {
        let value = match &binding.key {
            AssetKey::Address(value) | AssetKey::AssetPath(value) => value,
        };
        if value.is_empty() || value.len() > 1024 || value.chars().any(char::is_control) {
            return Err(FeatureError::IndexInvalidEntry);
        }
        let entries = self.entries.entry(feature).or_default();
        if !entries.contains(&binding) {
            if entries.len() >= 512 {
                return Err(FeatureError::IndexTooManyEntries);
            }
            entries.push(binding);
        }
        Ok(())
    }

    pub fn has_feature(&self, feature: Feature) -> bool {
        self.entries.contains_key(&feature)
    }
    pub fn requires_assets(&self, feature: Feature) -> Result<bool, FeatureError> {
        self.entries
            .get(&feature)
            .map(|entries| !entries.is_empty())
            .ok_or(FeatureError::ResourceNotFound)
    }
}

/// 依精確功能綁定尋找官方 AssetList，再取得所屬封包及必要 DependIDs。
/// 依賴圖允許循環（以已訪問節點去重），因為此處只下載檔案，不排序物件載入。
/// 所有資源限制都在呼叫網路下載前完成；不會選入其他未啟用功能的封包。
pub fn select<'a>(
    snapshot: &'a Snapshot,
    catalog: &FeatureCatalog,
    enabled: &BTreeSet<Feature>,
    max_files: usize,
    max_bytes: u64,
) -> Result<Vec<&'a Bundle>, FeatureError> {
    let mut result: Vec<&Bundle> = Vec::new();
    let mut seen: BTreeMap<String, &Bundle> = BTreeMap::new();
    let mut visited = BTreeSet::new();
    let mut total_bytes = 0u64;
    for feature in enabled {
        let requests = catalog
            .entries
            .get(feature)
            .ok_or(FeatureError::ResourceNotFound)?;
        for request in requests {
            let index = match request.package {
                Package::Data => &snapshot.data,
                Package::Main => &snapshot.main,
            };
            let asset_id = find_asset(index, &request.key)?;
            let mut stack = vec![asset_id];
            while let Some(id) = stack.pop() {
                if !visited.insert((request.package, id)) {
                    continue;
                }
                let bundle = index
                    .bundle_list
                    .get(id)
                    .ok_or(FeatureError::IndexInvalidEntry)?;
                if bundle.encrypted {
                    return Err(FeatureError::UnsupportedEncryption);
                }
                crate::verified_cache::validate_name(&bundle.bundle_name)?;
                official_cache::check_input(bundle)?;
                for &depend in &bundle.depend_ids {
                    if depend >= index.bundle_list.len() {
                        return Err(FeatureError::IndexInvalidEntry);
                    }
                    stack.push(depend);
                }
                let key = bundle.bundle_name.to_ascii_lowercase();
                if let Some(old) = seen.get(&key) {
                    if !old.file_hash.eq_ignore_ascii_case(&bundle.file_hash)
                        || !old.file_crc.eq_ignore_ascii_case(&bundle.file_crc)
                        || old.file_size != bundle.file_size
                    {
                        return Err(FeatureError::IndexDuplicatePath);
                    }
                    continue;
                }
                total_bytes = total_bytes
                    .checked_add(bundle.file_size)
                    .ok_or(FeatureError::DownloadQuotaExceeded)?;
                if result.len() >= max_files || total_bytes > max_bytes {
                    return Err(FeatureError::DownloadQuotaExceeded);
                }
                seen.insert(key, bundle);
                result.push(bundle);
            }
        }
    }
    Ok(result)
}

fn find_asset(index: &BundleIndex, key: &AssetKey) -> Result<usize, FeatureError> {
    let mut found = None;
    for asset in &index.asset_list {
        let matches = match key {
            AssetKey::Address(name) => asset.address == *name,
            AssetKey::AssetPath(path) => asset.asset_path == *path,
        };
        if matches {
            if found.is_some() {
                return Err(FeatureError::IndexDuplicatePath);
            }
            if asset.bundle_id >= index.bundle_list.len() {
                return Err(FeatureError::IndexInvalidEntry);
            }
            found = Some(asset.bundle_id);
        }
    }
    found.ok_or(FeatureError::ResourceNotFound)
}

/// 給功能事件使用的單次按需更新要求。UI 應於工作執行緒呼叫。
pub struct FeatureRequest<'a> {
    pub root: &'a Path,
    pub platform: Platform,
    pub executable: &'a str,
    pub feature: Feature,
    pub catalog: &'a FeatureCatalog,
    pub max_files: usize,
    pub max_bytes: u64,
}

#[derive(Debug, Clone, Copy, Eq, PartialEq)]
pub struct Progress {
    pub completed: usize,
    pub total: usize,
    pub downloaded: usize,
}

#[derive(Debug, Eq, PartialEq)]
pub struct FeatureResult {
    pub selected: usize,
    pub downloaded: usize,
    pub reused: usize,
    /// 無素材功能不要求官方索引查詢，因此不宣稱已確認版本。
    pub official_snapshot_checked: bool,
}

/// 在登入、地圖、戰鬥等 LaLa 功能事件發生時執行；只下載已綁定精確索引的封包。
/// 先查官方清單、全部預檢後逐檔下載、最後重新查詢確認沒有版本競態。
/// 官方 MD5／CRC32 與本機摘要用於損毀偵測，不宣稱官方數位簽章。
pub fn ensure_feature(request: &FeatureRequest<'_>) -> Result<FeatureResult, FeatureError> {
    ensure_with_progress(request, |_| {})
}

/// 進度只輸出計數，不包含遊戲內容、角色或本機絕對路徑。
pub fn ensure_with_progress(
    request: &FeatureRequest<'_>,
    on_progress: impl FnMut(Progress),
) -> Result<FeatureResult, FeatureError> {
    if !request.catalog.requires_assets(request.feature)? {
        return Ok(FeatureResult {
            selected: 0,
            downloaded: 0,
            reused: 0,
            official_snapshot_checked: false,
        });
    }
    let root_meta =
        std::fs::symlink_metadata(request.root).map_err(|_| FeatureError::StorageFailure)?;
    if !root_meta.file_type().is_dir() {
        return Err(FeatureError::CacheInvalidInput);
    }
    let first = manifest_snapshot::fetch(request.platform, request.executable)?;
    let enabled = BTreeSet::from([request.feature]);
    let selected = select(
        &first,
        request.catalog,
        &enabled,
        request.max_files,
        request.max_bytes,
    )?;
    let client = reqwest::blocking::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(Duration::from_secs(60))
        .build()
        .map_err(|_| FeatureError::RequestFailed)?;
    let total = selected.len();
    let (downloaded, reused) = fetch_selected(
        &selected,
        |bundle| {
            Ok(official_cache::fetch(
                &client,
                request.root,
                request.platform,
                &first.data_version,
                bundle,
            )?
            .downloaded)
        },
        on_progress,
    )?;
    let last = manifest_snapshot::fetch(request.platform, request.executable)?;
    if first.data_version != last.data_version
        || first.announced_executable != last.announced_executable
        || first.data_sha256 != last.data_sha256
        || first.main_sha256 != last.main_sha256
    {
        return Err(FeatureError::SnapshotChanged);
    }
    // 只記錄此功能實際用過且已驗證的封包，避免把整個資源庫誤當作已下載。
    offline_cache::save_selected(request.root, &last, &selected)?;
    Ok(FeatureResult {
        selected: total,
        downloaded,
        reused,
        official_snapshot_checked: true,
    })
}

fn fetch_selected(
    selected: &[&Bundle],
    mut fetch: impl FnMut(&Bundle) -> Result<bool, FeatureError>,
    mut on_progress: impl FnMut(Progress),
) -> Result<(usize, usize), FeatureError> {
    let mut downloaded = 0;
    let mut reused = 0;
    for (i, bundle) in selected.iter().enumerate() {
        if fetch(bundle)? {
            downloaded += 1;
            if i + 1 != selected.len() {
                thread::sleep(REQUEST_GAP);
            }
        } else {
            reused += 1;
        }
        on_progress(Progress {
            completed: i + 1,
            total: selected.len(),
            downloaded,
        });
    }
    Ok((downloaded, reused))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::bundle_index::{Asset, Bundle};
    fn bundle(name: &str, id: u8, depends: Vec<usize>) -> Bundle {
        Bundle {
            bundle_name: name.into(),
            unity_crc: 0,
            file_hash: format!("{id:032x}"),
            file_crc: format!("{id:08x}"),
            file_size: 10,
            encrypted: false,
            tags: vec![],
            depend_ids: depends,
        }
    }
    fn index(package: &str, bundle_list: Vec<Bundle>, addresses: &[(&str, usize)]) -> BundleIndex {
        BundleIndex {
            file_version: "2.2.5".into(),
            package_name: package.into(),
            package_version: "v1".into(),
            asset_list: addresses
                .iter()
                .map(|(name, id)| Asset {
                    address: (*name).into(),
                    asset_path: format!("Assets/{name}"),
                    asset_guid: String::new(),
                    asset_tags: vec![],
                    bundle_id: *id,
                })
                .collect(),
            bundle_list,
        }
    }
    fn snapshot() -> Snapshot {
        Snapshot {
            data_version: "1.3.21".into(),
            announced_executable: "1.3.0".into(),
            data_sha256: "a".repeat(64),
            main_sha256: "b".repeat(64),
            data: index(
                "DataPackage",
                vec![
                    bundle("map.bundle", 1, vec![1]),
                    bundle("shared.bundle", 2, vec![0]),
                    bundle("unrelated.bundle", 3, vec![]),
                ],
                &[("map-asset", 0), ("unrelated-asset", 2)],
            ),
            main: index(
                "MainPackage",
                vec![bundle("battle.bundle", 4, vec![])],
                &[("battle-asset", 0)],
            ),
        }
    }
    fn catalog() -> FeatureCatalog {
        let mut catalog = FeatureCatalog::default();
        catalog
            .bind(
                Feature::Map,
                AssetBinding {
                    package: Package::Data,
                    key: AssetKey::Address("map-asset".into()),
                },
            )
            .unwrap();
        catalog
            .bind(
                Feature::Battle,
                AssetBinding {
                    package: Package::Main,
                    key: AssetKey::AssetPath("Assets/battle-asset".into()),
                },
            )
            .unwrap();
        catalog
    }

    #[test]
    fn feature_ids_cover_legacy_scope_without_duplicates() {
        let ids: BTreeSet<&str> = Feature::ALL.into_iter().map(Feature::id).collect();
        assert_eq!(ids.len(), Feature::ALL.len());
        for expected in [
            "account",
            "character",
            "map",
            "navigation",
            "portal",
            "battle",
            "inventory",
            "storage",
            "expedition",
            "social",
            "party",
            "pet",
            "npc",
            "shop",
            "alchemy",
            "crafting",
            "dungeon",
            "cooperative",
            "maintenance",
            "analytics",
            "housing",
        ] {
            assert!(ids.contains(expected), "missing {expected}");
        }
        let catalog = FeatureCatalog::default();
        assert!(Feature::ALL
            .iter()
            .all(|feature| !catalog.has_feature(*feature)));
    }

    #[test]
    fn selects_only_feature_and_its_cyclic_dependencies() {
        let snapshot = snapshot();
        let selected = select(
            &snapshot,
            &catalog(),
            &BTreeSet::from([Feature::Map]),
            3,
            30,
        )
        .unwrap();
        assert_eq!(selected.len(), 2);
        assert!(selected.iter().any(|b| b.bundle_name == "map.bundle"));
        assert!(selected.iter().any(|b| b.bundle_name == "shared.bundle"));
        assert!(!selected.iter().any(|b| b.bundle_name == "unrelated.bundle"));
        assert!(!selected.iter().any(|b| b.bundle_name == "battle.bundle"));
    }

    #[test]
    fn combines_only_requested_features_without_duplicates() {
        let snapshot = snapshot();
        let selected = select(
            &snapshot,
            &catalog(),
            &BTreeSet::from([Feature::Map, Feature::Battle]),
            3,
            30,
        )
        .unwrap();
        assert_eq!(selected.len(), 3);
    }

    #[test]
    fn unknown_or_ambiguous_binding_fails_closed() {
        let snapshot = snapshot();
        let mut catalog = catalog();
        assert_eq!(
            select(
                &snapshot,
                &catalog,
                &BTreeSet::from([Feature::Pet]),
                10,
                100
            )
            .unwrap_err(),
            FeatureError::ResourceNotFound
        );
        catalog
            .bind(
                Feature::Pet,
                AssetBinding {
                    package: Package::Data,
                    key: AssetKey::Address("unknown".into()),
                },
            )
            .unwrap();
        assert_eq!(
            select(
                &snapshot,
                &catalog,
                &BTreeSet::from([Feature::Pet]),
                10,
                100
            )
            .unwrap_err(),
            FeatureError::ResourceNotFound
        );
        let mut duplicated = snapshot.clone();
        duplicated
            .data
            .asset_list
            .push(duplicated.data.asset_list[0].clone());
        assert_eq!(
            select(
                &duplicated,
                &catalog,
                &BTreeSet::from([Feature::Map]),
                10,
                100
            )
            .unwrap_err(),
            FeatureError::IndexDuplicatePath
        );
    }

    #[test]
    fn checks_all_quota_and_encryption_before_download() {
        let snapshot = snapshot();
        assert_eq!(
            select(
                &snapshot,
                &catalog(),
                &BTreeSet::from([Feature::Map]),
                1,
                30
            )
            .unwrap_err(),
            FeatureError::DownloadQuotaExceeded
        );
        assert_eq!(
            select(
                &snapshot,
                &catalog(),
                &BTreeSet::from([Feature::Map]),
                3,
                10
            )
            .unwrap_err(),
            FeatureError::DownloadQuotaExceeded
        );
        let mut protected = snapshot.clone();
        protected.data.bundle_list[1].encrypted = true;
        assert_eq!(
            select(
                &protected,
                &catalog(),
                &BTreeSet::from([Feature::Map]),
                3,
                30
            )
            .unwrap_err(),
            FeatureError::UnsupportedEncryption
        );
    }

    #[test]
    fn uses_cache_and_reports_only_selected_downloads() {
        let snapshot = snapshot();
        let selected = select(
            &snapshot,
            &catalog(),
            &BTreeSet::from([Feature::Map]),
            3,
            30,
        )
        .unwrap();
        let mut calls = 0;
        let mut progress = Vec::new();
        let (downloaded, reused) = fetch_selected(
            &selected,
            |_| {
                calls += 1;
                Ok(calls == 1)
            },
            |value| progress.push(value),
        )
        .unwrap();
        assert_eq!((downloaded, reused), (1, 1));
        assert_eq!(calls, 2);
        assert_eq!(progress.last().unwrap().total, 2);
    }

    #[test]
    fn empty_feature_must_be_explicit_and_does_not_access_remote() {
        let mut catalog = FeatureCatalog::default();
        catalog.register_no_assets(Feature::Account);
        let root = std::path::Path::new("not-a-real-cache-directory");
        let request = FeatureRequest {
            root,
            platform: Platform::Windows,
            executable: "1.3.0",
            feature: Feature::Account,
            catalog: &catalog,
            max_files: 1,
            max_bytes: 1,
        };
        assert_eq!(
            ensure_feature(&request).unwrap(),
            FeatureResult {
                selected: 0,
                downloaded: 0,
                reused: 0,
                official_snapshot_checked: false,
            }
        );
    }
}
