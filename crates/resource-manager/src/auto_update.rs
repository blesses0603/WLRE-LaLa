//! 在應用程式執行期間，定期查詢官方版本並下載缺少或損毀的資源。
use crate::{
    bundle_index::Bundle,
    feature_resources::{self, Feature, FeatureCatalog},
    manifest_snapshot::{self, Snapshot},
    official_cache, offline_cache,
    scheduler::Scheduler,
    version_map::Platform,
};
use std::{
    collections::BTreeSet,
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc::{self, Receiver, RecvTimeoutError, Sender},
        Arc,
    },
    thread,
    time::{Duration, Instant},
};
pub use wlre_core_observability::ErrorCode as UpdateError;
const REQUEST_GAP: Duration = Duration::from_millis(200);

/// 呼叫端提供私有可信快取目錄；不得由其他不可信程序同時修改。
/// 預設僅觀察版本，不會批量下載所有封包；只有明確啟用並綁定的功能可更新。
#[derive(Debug)]
pub struct Config {
    pub root: PathBuf,
    pub platform: Platform,
    pub executable: String,
    pub interval: Duration,
    pub max_files: usize,
    pub max_bytes: u64,
    pub catalog: FeatureCatalog,
    pub enabled_features: BTreeSet<Feature>,
}

impl Config {
    /// 預設只觀察版本；加入精確功能資產綁定後才會下載相關封包。
    pub fn new(root: PathBuf, platform: Platform, executable: String) -> Self {
        Self {
            root,
            platform,
            executable,
            interval: Duration::from_secs(3600),
            max_files: 10_000,
            max_bytes: 8 * 1024 * 1024 * 1024,
            catalog: FeatureCatalog::default(),
            enabled_features: BTreeSet::new(),
        }
    }

    /// 要求程式持續追蹤特定功能，且此功能已由呼叫端提供官方索引精確綁定。
    /// 程序執行中的即時功能需求，應使用 feature_resources::ensure_feature。
    pub fn enable_feature(&mut self, feature: Feature) -> Result<(), UpdateError> {
        if !self.catalog.has_feature(feature) {
            return Err(UpdateError::ResourceNotFound);
        }
        self.enabled_features.insert(feature);
        Ok(())
    }

    /// 由平台已建立的私有快取位置啟動；適用於桌面與 Android 平台適配層。
    pub fn from_private_location(
        location: &crate::platform_storage::CacheLocation,
        platform: Platform,
        executable: String,
    ) -> Self {
        Self::new(location.root().to_owned(), platform, executable)
    }
}

/// 結構化事件供平台呈現與記錄；沒有封包路徑或遊戲內容。
#[derive(Debug, Clone, serde::Serialize)]
#[serde(tag = "event", rename_all = "SCREAMING_SNAKE_CASE")]
pub enum Event {
    VersionObserved {
        data_version: String,
        installed_executable: String,
        announced_executable: String,
        data_package: String,
        main_package: String,
        changed: bool,
        first_observation: bool,
    },
    Progress {
        completed: usize,
        total: usize,
        downloaded: usize,
    },
    Completed {
        total: usize,
        downloaded: usize,
    },
    /// 網路失敗時僅代表舊快取仍可離線使用，絕不代表官方最新。
    OfflineCacheAvailable {
        data_version: String,
        bundle_count: usize,
    },
    Failed {
        error: UpdateError,
    },
    Stopped,
}
#[derive(Clone, Debug, Eq, PartialEq)]
struct Identity {
    data_version: String,
    announced_executable: String,
    data_sha: String,
    main_sha: String,
}
impl From<&Snapshot> for Identity {
    fn from(value: &Snapshot) -> Self {
        Self {
            data_version: value.data_version.clone(),
            announced_executable: value.announced_executable.clone(),
            data_sha: value.data_sha256.clone(),
            main_sha: value.main_sha256.clone(),
        }
    }
}

/// 前景執行期間運作的背景工作；預設不下載任何遊戲封包。
/// 可在啟動前註冊功能進行定期更新；新增功能即時需求使用獨立按需 API。
/// 停止會在目前清單查詢或單檔請求完成或逾時後生效，並阻止後續封包下載。
pub struct AutoUpdater {
    stop: Arc<AtomicBool>,
    wake: Sender<()>,
}
impl AutoUpdater {
    /// 啟動後立即檢查，其後依間隔檢查；失敗時按有限退避重試。
    /// 最終 `Completed` 只代表快取下載與官方校驗一致，並非防竄改認證或遊戲相容驗收。
    pub fn start(config: Config) -> Result<(Self, Receiver<Event>), UpdateError> {
        let mut scheduler = Scheduler::new(config.interval, Duration::ZERO)?;
        if config.max_files == 0 || config.max_bytes == 0 {
            return Err(UpdateError::DownloadQuotaExceeded);
        }
        let metadata =
            std::fs::symlink_metadata(&config.root).map_err(|_| UpdateError::StorageFailure)?;
        if !metadata.file_type().is_dir() {
            return Err(UpdateError::CacheInvalidInput);
        }
        let client = reqwest::blocking::Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .timeout(Duration::from_secs(60))
            .build()
            .map_err(|_| UpdateError::RequestFailed)?;
        let (tx, events) = mpsc::channel();
        let (wake, wake_rx) = mpsc::channel();
        let stop = Arc::new(AtomicBool::new(false));
        let signal = stop.clone();
        thread::Builder::new()
            .name("wlre-resource-update".into())
            .spawn(move || {
                let start = Instant::now();
                let mut previous: Option<Identity> = None;
                loop {
                    if signal.load(Ordering::Acquire) {
                        break;
                    }
                    let now = start.elapsed();
                    if scheduler.begin(now) {
                        let operations = OfficialOperations { client: &client };
                        let result = run_cycle(
                            &config,
                            &operations,
                            &tx,
                            &wake_rx,
                            &signal,
                            previous.as_ref(),
                        );
                        let success = result.is_ok();
                        if let Ok(identity) = &result {
                            previous = Some(identity.clone());
                        }
                        if let Err(error) = result {
                            if error == UpdateError::UpdateCancelled {
                                break;
                            }
                            if matches!(
                                error,
                                UpdateError::RequestFailed | UpdateError::UnexpectedResponse
                            ) {
                                if let Ok(Some(cache)) = offline_cache::verify(&config.root) {
                                    let _ = tx.send(Event::OfflineCacheAvailable {
                                        data_version: cache.data_version,
                                        bundle_count: cache.bundle_count,
                                    });
                                }
                            }
                            let _ = tx.send(Event::Failed { error });
                        }
                        if scheduler.finish(start.elapsed(), success).is_err() {
                            let _ = tx.send(Event::Failed {
                                error: UpdateError::ScheduleInvalid,
                            });
                            break;
                        }
                    }
                    let wait = scheduler.next_due().saturating_sub(start.elapsed());
                    match wake_rx.recv_timeout(wait) {
                        Ok(()) | Err(RecvTimeoutError::Disconnected) => break,
                        Err(RecvTimeoutError::Timeout) => {}
                    }
                }
                let _ = tx.send(Event::Stopped);
            })
            .map_err(|_| UpdateError::StorageFailure)?;
        Ok((Self { stop, wake }, events))
    }
    pub fn request_stop(&self) {
        self.stop.store(true, Ordering::Release);
        let _ = self.wake.send(());
    }
}
impl Drop for AutoUpdater {
    fn drop(&mut self) {
        self.request_stop();
    }
}

trait Operations {
    fn snapshot(&self, config: &Config) -> Result<Snapshot, UpdateError>;
    fn download(
        &self,
        config: &Config,
        version: &str,
        bundle: &Bundle,
    ) -> Result<bool, UpdateError>;
    fn record_completed(
        &self,
        _config: &Config,
        _snapshot: &Snapshot,
        _selected: &[&Bundle],
    ) -> Result<(), UpdateError> {
        Ok(())
    }
}
struct OfficialOperations<'a> {
    client: &'a reqwest::blocking::Client,
}
impl Operations for OfficialOperations<'_> {
    fn snapshot(&self, config: &Config) -> Result<Snapshot, UpdateError> {
        manifest_snapshot::fetch(config.platform, &config.executable)
    }
    fn download(
        &self,
        config: &Config,
        version: &str,
        bundle: &Bundle,
    ) -> Result<bool, UpdateError> {
        Ok(
            official_cache::fetch(self.client, &config.root, config.platform, version, bundle)?
                .downloaded,
        )
    }
    fn record_completed(
        &self,
        config: &Config,
        snapshot: &Snapshot,
        selected: &[&Bundle],
    ) -> Result<(), UpdateError> {
        offline_cache::save_selected(&config.root, snapshot, selected)
    }
}

fn run_cycle(
    config: &Config,
    operations: &impl Operations,
    tx: &Sender<Event>,
    wake: &Receiver<()>,
    stop: &AtomicBool,
    previous: Option<&Identity>,
) -> Result<Identity, UpdateError> {
    if stop.load(Ordering::Acquire) {
        return Err(UpdateError::UpdateCancelled);
    }
    let snapshot = operations.snapshot(config)?;
    let identity = Identity::from(&snapshot);
    let changed = previous.is_some_and(|old| old != &identity);
    let _ = tx.send(Event::VersionObserved {
        data_version: snapshot.data_version.clone(),
        installed_executable: config.executable.clone(),
        announced_executable: snapshot.announced_executable.clone(),
        data_package: snapshot.data.package_version.clone(),
        main_package: snapshot.main.package_version.clone(),
        changed,
        first_observation: previous.is_none(),
    });
    let bundles = feature_resources::select(
        &snapshot,
        &config.catalog,
        &config.enabled_features,
        config.max_files,
        config.max_bytes,
    )?;
    let total = bundles.len();
    let mut downloaded = 0usize;
    for (index, bundle) in bundles.iter().enumerate() {
        if stop.load(Ordering::Acquire) {
            return Err(UpdateError::UpdateCancelled);
        }
        let downloaded_now = operations.download(config, &snapshot.data_version, bundle)?;
        if downloaded_now {
            downloaded += 1;
        }
        let _ = tx.send(Event::Progress {
            completed: index + 1,
            total,
            downloaded,
        });
        if downloaded_now
            && matches!(
                wake.recv_timeout(REQUEST_GAP),
                Ok(()) | Err(RecvTimeoutError::Disconnected)
            )
        {
            return Err(UpdateError::UpdateCancelled);
        }
    }
    let latest = operations.snapshot(config)?;
    if Identity::from(&latest) != identity {
        return Err(UpdateError::SnapshotChanged);
    }
    if !bundles.is_empty() {
        operations.record_completed(config, &latest, &bundles)?;
        let _ = tx.send(Event::Completed { total, downloaded });
    }
    Ok(identity)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn reports_structured_version_and_error_events() {
        let event = Event::VersionObserved {
            data_version: "1.3.22".into(),
            installed_executable: "1.3.0".into(),
            announced_executable: "1.4.0".into(),
            data_package: "2".into(),
            main_package: "3".into(),
            changed: true,
            first_observation: false,
        };
        let value = serde_json::to_value(event).unwrap();
        assert_eq!(value["event"], "VERSION_OBSERVED");
        assert_eq!(value["changed"], true);
        let failure = serde_json::to_value(Event::Failed {
            error: UpdateError::CacheIntegrityFailure,
        })
        .unwrap();
        assert_eq!(failure["error"], "CACHE_INTEGRITY_FAILURE");
    }
    struct MockOperations {
        version: std::cell::Cell<u8>,
        downloads: std::cell::RefCell<Vec<String>>,
        cyclic: bool,
    }
    impl Operations for MockOperations {
        fn snapshot(&self, _: &Config) -> Result<Snapshot, UpdateError> {
            use crate::bundle_index::BundleIndex;
            fn index(package: &str, version: u8, cyclic: bool) -> BundleIndex {
                BundleIndex {
                    file_version: "2.2.5".into(),
                    package_name: package.into(),
                    package_version: format!("rev_{version}"),
                    asset_list: vec![crate::bundle_index::Asset {
                        address: format!("{package}-needed"),
                        asset_path: format!("Assets/{package}"),
                        asset_guid: String::new(),
                        asset_tags: vec![],
                        bundle_id: 0,
                    }],
                    bundle_list: vec![Bundle {
                        bundle_name: format!("{package}.bundle"),
                        unity_crc: 0,
                        file_hash: "a".repeat(32),
                        file_crc: "b".repeat(8),
                        file_size: 3,
                        encrypted: false,
                        tags: vec![],
                        depend_ids: if cyclic { vec![0] } else { vec![] },
                    }],
                }
            }
            let v = self.version.get();
            Ok(Snapshot {
                data_version: format!("1.3.{v}"),
                announced_executable: format!("1.4.{v}"),
                data_sha256: format!("data{v}"),
                main_sha256: format!("main{v}"),
                data: index("DataPackage", v, self.cyclic),
                main: index("MainPackage", v, self.cyclic),
            })
        }
        fn download(
            &self,
            _: &Config,
            version: &str,
            bundle: &Bundle,
        ) -> Result<bool, UpdateError> {
            self.downloads
                .borrow_mut()
                .push(format!("{version}/{}", bundle.bundle_name));
            Ok(true)
        }
    }
    #[test]
    fn tracks_changes_and_downloads_only_enabled_feature_bundles() {
        let root = tempfile::tempdir().unwrap();
        let mut config = Config::new(root.path().to_owned(), Platform::Windows, "1.3.0".into());
        config
            .catalog
            .bind(
                Feature::Map,
                crate::feature_resources::AssetBinding {
                    package: crate::bundle_index::Package::Data,
                    key: crate::feature_resources::AssetKey::Address("DataPackage-needed".into()),
                },
            )
            .unwrap();
        config.enable_feature(Feature::Map).unwrap();
        let ops = MockOperations {
            version: std::cell::Cell::new(21),
            downloads: std::cell::RefCell::new(Vec::new()),
            cyclic: false,
        };
        let (event_tx, event_rx) = mpsc::channel();
        let (_wake_tx, wake_rx) = mpsc::channel();
        let stop = AtomicBool::new(false);
        let first = run_cycle(&config, &ops, &event_tx, &wake_rx, &stop, None).unwrap();
        ops.version.set(22);
        run_cycle(&config, &ops, &event_tx, &wake_rx, &stop, Some(&first)).unwrap();
        assert_eq!(ops.downloads.borrow().len(), 2);
        assert!(ops
            .downloads
            .borrow()
            .iter()
            .all(|name| name.contains("DataPackage")));
        assert!(ops
            .downloads
            .borrow()
            .iter()
            .any(|name| name.starts_with("1.3.22/")));
        assert!(event_rx.try_iter().any(|event|matches!(event,Event::VersionObserved {data_version,changed:true,..} if data_version=="1.3.22")));
    }
    #[test]
    fn selected_feature_allows_cyclic_dependency_graph() {
        let root = tempfile::tempdir().unwrap();
        let mut config = Config::new(root.path().to_owned(), Platform::Windows, "1.3.0".into());
        config
            .catalog
            .bind(
                Feature::Map,
                crate::feature_resources::AssetBinding {
                    package: crate::bundle_index::Package::Data,
                    key: crate::feature_resources::AssetKey::Address("DataPackage-needed".into()),
                },
            )
            .unwrap();
        config.enable_feature(Feature::Map).unwrap();
        let ops = MockOperations {
            version: std::cell::Cell::new(21),
            downloads: std::cell::RefCell::new(Vec::new()),
            cyclic: true,
        };
        let (tx, _) = mpsc::channel();
        let (_wake_tx, wake_rx) = mpsc::channel();
        let stop = AtomicBool::new(false);
        assert!(run_cycle(&config, &ops, &tx, &wake_rx, &stop, None).is_ok());
        assert_eq!(ops.downloads.borrow().len(), 1);
    }

    #[test]
    fn refuses_quota_before_downloading_any_bundle() {
        let root = tempfile::tempdir().unwrap();
        let mut config = Config::new(root.path().to_owned(), Platform::Windows, "1.3.0".into());
        config
            .catalog
            .bind(
                Feature::Map,
                crate::feature_resources::AssetBinding {
                    package: crate::bundle_index::Package::Data,
                    key: crate::feature_resources::AssetKey::Address("DataPackage-needed".into()),
                },
            )
            .unwrap();
        config
            .catalog
            .bind(
                Feature::Battle,
                crate::feature_resources::AssetBinding {
                    package: crate::bundle_index::Package::Main,
                    key: crate::feature_resources::AssetKey::Address("MainPackage-needed".into()),
                },
            )
            .unwrap();
        config.enable_feature(Feature::Map).unwrap();
        config.enable_feature(Feature::Battle).unwrap();
        config.max_files = 1;
        let ops = MockOperations {
            version: std::cell::Cell::new(21),
            downloads: std::cell::RefCell::new(Vec::new()),
            cyclic: false,
        };
        let (event_tx, _) = mpsc::channel();
        let (_wake_tx, wake_rx) = mpsc::channel();
        let stop = AtomicBool::new(false);
        assert!(matches!(
            run_cycle(&config, &ops, &event_tx, &wake_rx, &stop, None),
            Err(UpdateError::DownloadQuotaExceeded)
        ));
        assert!(ops.downloads.borrow().is_empty());
    }

    #[test]
    fn default_configuration_only_observes_versions_without_downloads() {
        let root = tempfile::tempdir().unwrap();
        let config = Config::new(root.path().to_owned(), Platform::Windows, "1.3.0".into());
        let ops = MockOperations {
            version: std::cell::Cell::new(21),
            downloads: std::cell::RefCell::new(Vec::new()),
            cyclic: false,
        };
        let (events, receiver) = mpsc::channel();
        let (_wake_tx, wake_rx) = mpsc::channel();
        let stop = AtomicBool::new(false);
        run_cycle(&config, &ops, &events, &wake_rx, &stop, None).unwrap();
        assert!(ops.downloads.borrow().is_empty());
        assert!(receiver
            .try_iter()
            .any(|event| matches!(event, Event::VersionObserved { .. })));
    }

    #[test]
    fn refuses_invalid_configuration_without_starting_a_worker() {
        let dir = tempfile::tempdir().unwrap();
        let mut config = Config::new(dir.path().to_owned(), Platform::Windows, "1.3.0".into());
        config.interval = Duration::from_secs(1);
        assert!(matches!(
            AutoUpdater::start(config),
            Err(UpdateError::ScheduleInvalid)
        ));
    }
}
