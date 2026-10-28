//! 取得同一版本觀察期間的兩份官方二進位清單。
use crate::{binary_manifest, bundle_index::BundleIndex, version_map};
use serde::{Deserialize, Serialize};
use std::io::Read;
pub use wlre_core_observability::ErrorCode as SnapshotError;

const BASE: &str = "https://wlreftpsrc.chinesegamer.net/WLN/TW/";
const MANIFEST_LIMIT: usize = 16 * 1024 * 1024;

/// 包含兩份已通過 CRC32 與格式檢查的清單；CRC 不提供防竄改保證。
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Snapshot {
    pub data_version: String,
    pub announced_executable: String,
    pub data_sha256: String,
    pub main_sha256: String,
    pub data: BundleIndex,
    pub main: BundleIndex,
}

trait Source {
    fn get(&self, path: &str, limit: usize) -> Result<Vec<u8>, SnapshotError>;
}
struct OfficialSource(reqwest::blocking::Client);
impl Source for OfficialSource {
    fn get(&self, path: &str, limit: usize) -> Result<Vec<u8>, SnapshotError> {
        let response = self
            .0
            .get(format!("{BASE}{path}"))
            .send()
            .map_err(|_| SnapshotError::RequestFailed)?;
        if response.status() != reqwest::StatusCode::OK {
            return Err(SnapshotError::UnexpectedResponse);
        }
        if response.content_length().is_some_and(|n| n > limit as u64) {
            return Err(SnapshotError::IndexTooLarge);
        }
        let mut body = Vec::new();
        response
            .take(limit as u64 + 1)
            .read_to_end(&mut body)
            .map_err(|_| SnapshotError::RequestFailed)?;
        if body.len() > limit {
            return Err(SnapshotError::IndexTooLarge);
        }
        Ok(body)
    }
}

/// 查詢指定平台和執行檔版本，下載兩份官方清單並再次確認版本對照。
/// 依官方對照值組成已觀察的目錄結構；未知或不相容格式會拒絕。
/// 須由呼叫端負責排程及節流；同步操作。CRC 不驗證內容是否遭惡意替換。
pub fn fetch(platform: version_map::Platform, executable: &str) -> Result<Snapshot, SnapshotError> {
    let client = reqwest::blocking::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .map_err(|_| SnapshotError::RequestFailed)?;
    fetch_from(&OfficialSource(client), platform, executable)
}

fn text(bytes: Vec<u8>) -> Result<String, SnapshotError> {
    let s = std::str::from_utf8(&bytes)
        .map_err(|_| SnapshotError::IndexInvalidEncoding)?
        .trim();
    if s.is_empty()
        || s.len() > 128
        || !s
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'.')
    {
        return Err(SnapshotError::IndexInvalidEntry);
    }
    Ok(s.to_owned())
}

fn fetch_from(
    source: &impl Source,
    platform: version_map::Platform,
    executable: &str,
) -> Result<Snapshot, SnapshotError> {
    let (map, directory) = match platform {
        version_map::Platform::Windows => ("ResourcePath_PC.dat", "ResourcesPC"),
        version_map::Platform::Android => ("ResourcePath_ANDROID.dat", "ResourcesAndroid"),
    };
    let initial_mapping = source.get(map, 16 * 1024)?;
    if !version_map::valid_version(executable) {
        return Err(SnapshotError::IndexInvalidEntry);
    }
    let (announced_executable, data_version) = version_map::select_latest(&initial_mapping)?;
    let root = format!("{data_version}/{directory}/AssetBundle/");
    let revision = |name: &str| text(source.get(&format!("{root}{name}.version"), 128)?);
    let data_revision = revision("DataPackage")?;
    let main_revision = revision("MainPackage")?;
    let hash = |name: &str| text(source.get(&format!("{root}{name}.hash"), 8)?);
    let data_hash = hash("DataPackage")?;
    let data_bytes = source.get(&format!("{root}DataPackage.bytes"), MANIFEST_LIMIT)?;
    let data = binary_manifest::parse(&data_bytes, &data_hash, "DataPackage", &data_revision)?;
    let main_hash = hash("MainPackage")?;
    let main_bytes = source.get(&format!("{root}MainPackage.bytes"), MANIFEST_LIMIT)?;
    let main = binary_manifest::parse(&main_bytes, &main_hash, "MainPackage", &main_revision)?;
    let final_data = revision("DataPackage")?;
    let final_main = revision("MainPackage")?;
    let final_mapping = source.get(map, 16 * 1024)?;
    let (final_executable, final_version) = version_map::select_latest(&final_mapping)?;
    let final_data_hash = hash("DataPackage")?;
    let final_main_hash = hash("MainPackage")?;
    if data_version != final_version
        || announced_executable != final_executable
        || data_revision != final_data
        || main_revision != final_main
        || !data_hash.eq_ignore_ascii_case(&final_data_hash)
        || !main_hash.eq_ignore_ascii_case(&final_main_hash)
    {
        return Err(SnapshotError::SnapshotChanged);
    }
    use sha2::{Digest, Sha256};
    Ok(Snapshot {
        data_version,
        announced_executable,
        data_sha256: format!("{:x}", Sha256::digest(&data_bytes)),
        main_sha256: format!("{:x}", Sha256::digest(&main_bytes)),
        data,
        main,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;
    fn string(out: &mut Vec<u8>, s: &str) {
        out.extend_from_slice(&(s.len() as u16).to_le_bytes());
        out.extend_from_slice(s.as_bytes());
    }
    fn manifest(name: &str) -> Vec<u8> {
        let mut b = Vec::new();
        b.extend_from_slice(&0x00594f4fu32.to_le_bytes());
        string(&mut b, "2.2.5");
        b.extend_from_slice(&[0, 0, 0]);
        b.extend_from_slice(&1i32.to_le_bytes());
        b.extend_from_slice(&0i32.to_le_bytes());
        string(&mut b, "pipeline");
        string(&mut b, name);
        string(&mut b, "rev_1");
        string(&mut b, "");
        b.extend_from_slice(&0i32.to_le_bytes());
        b.extend_from_slice(&1i32.to_le_bytes());
        string(&mut b, "test.bundle");
        b.extend_from_slice(&0u32.to_le_bytes());
        string(&mut b, "0123456789abcdef0123456789abcdef");
        string(&mut b, "00000000");
        b.extend_from_slice(&1i64.to_le_bytes());
        b.push(0);
        b.extend_from_slice(&0u16.to_le_bytes());
        b.extend_from_slice(&0u16.to_le_bytes());
        b
    }
    struct Mock {
        change: bool,
        corrupt: bool,
        versions: Cell<u8>,
    }
    impl Source for Mock {
        fn get(&self, path: &str, _limit: usize) -> Result<Vec<u8>, SnapshotError> {
            if path.ends_with(".dat") {
                return Ok(br#"[{"ExeVer":"1.3.0","DataVer":"1.3.21"},]"#.to_vec());
            }
            let name = if path.contains("DataPackage") {
                "DataPackage"
            } else {
                "MainPackage"
            };
            if path.ends_with(".version") {
                let n = self.versions.get();
                self.versions.set(n + 1);
                return Ok(if self.change && n >= 2 {
                    b"rev_2".to_vec()
                } else {
                    b"rev_1".to_vec()
                });
            }
            let bytes = manifest(name);
            if path.ends_with(".hash") {
                let hash = if self.corrupt {
                    0
                } else {
                    crc32fast::hash(&bytes)
                };
                return Ok(hash
                    .to_le_bytes()
                    .iter()
                    .map(|x| format!("{x:02x}"))
                    .collect::<String>()
                    .into_bytes());
            }
            if path.ends_with(".bytes") {
                return Ok(bytes);
            }
            Err(SnapshotError::UnexpectedResponse)
        }
    }
    #[test]
    #[ignore = "需對官方固定端點執行低負載驗證"]
    fn official_current_snapshot_smoke() {
        let snapshot = fetch(version_map::Platform::Windows, "1.3.0").unwrap();
        assert!(!snapshot.data.bundle_list.is_empty());
        assert!(!snapshot.main.bundle_list.is_empty());
    }

    #[test]
    fn fetches_two_checked_manifests_and_rechecks_revisions() {
        let source = Mock {
            change: false,
            corrupt: false,
            versions: Cell::new(0),
        };
        let result = fetch_from(&source, version_map::Platform::Windows, "1.3.0").unwrap();
        assert_eq!(result.data.package_name, "DataPackage");
        assert_eq!(result.main.package_name, "MainPackage");
        assert_eq!(source.versions.get(), 4);
    }
    #[test]
    fn follows_new_version_announced_by_official_mapping() {
        struct NewVersion(Mock);
        impl Source for NewVersion {
            fn get(&self, path: &str, limit: usize) -> Result<Vec<u8>, SnapshotError> {
                if path.ends_with(".dat") {
                    return Ok(br#"[{"ExeVer":"1.3.0","DataVer":"1.3.21"},{"ExeVer":"1.4.0","DataVer":"1.3.22"},]"#.to_vec());
                }
                if !path.starts_with("1.3.22/") {
                    return Err(SnapshotError::UnexpectedResponse);
                }
                self.0.get(path, limit)
            }
        }
        let source = NewVersion(Mock {
            change: false,
            corrupt: false,
            versions: Cell::new(0),
        });
        let result = fetch_from(&source, version_map::Platform::Windows, "1.3.0").unwrap();
        assert_eq!(result.data_version, "1.3.22");
        assert_eq!(result.announced_executable, "1.4.0");
    }

    #[test]
    fn refuses_mixed_versions_and_corrupt_manifest() {
        let source = Mock {
            change: true,
            corrupt: false,
            versions: Cell::new(0),
        };
        assert!(matches!(
            fetch_from(&source, version_map::Platform::Windows, "1.3.0"),
            Err(SnapshotError::SnapshotChanged)
        ));
        let source = Mock {
            change: false,
            corrupt: true,
            versions: Cell::new(0),
        };
        assert!(matches!(
            fetch_from(&source, version_map::Platform::Windows, "1.3.0"),
            Err(SnapshotError::CacheIntegrityFailure)
        ));
    }
}
