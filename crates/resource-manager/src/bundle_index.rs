//! 觀察到的資源包 JSON 結構；不選擇遊戲版本，不執行下載或提取。

use serde::Deserialize;
use std::collections::BTreeSet;
pub use wlre_core_observability::ErrorCode as IndexError;

const MAX_BYTES: usize = 16 * 1024 * 1024;
const MAX_BUNDLES: usize = 100_000;
const MAX_ASSETS: usize = 500_000;

/// 保留實際索引中的清單順序：關聯及相依編號以此順序索引。
#[derive(Debug, Deserialize)]
#[serde(rename_all = "PascalCase")]
pub struct BundleIndex {
    pub file_version: String,
    pub package_name: String,
    pub package_version: String,
    pub asset_list: Vec<Asset>,
    pub bundle_list: Vec<Bundle>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "PascalCase")]
pub struct Asset {
    pub address: String,
    pub asset_path: String,
    #[serde(rename = "AssetGUID")]
    pub asset_guid: String,
    pub asset_tags: Vec<String>,
    #[serde(rename = "BundleID")]
    pub bundle_id: usize,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "PascalCase")]
pub struct Bundle {
    pub bundle_name: String,
    #[serde(rename = "UnityCRC")]
    pub unity_crc: u32,
    pub file_hash: String,
    #[serde(rename = "FileCRC")]
    pub file_crc: String,
    pub file_size: u64,
    pub encrypted: bool,
    pub tags: Vec<String>,
    #[serde(rename = "DependIDs")]
    pub depend_ids: Vec<usize>,
}

/// 觀察到的單一版本索引；不代表官方目前使用或最新版本。
const OBSERVED_INDEX_URL: &str =
    "https://wlreftpsrc.chinesegamer.net/WLN/TW/1.3.22/ResourcesPC/AssetBundle/DataPackage.json";

/// 僅包含目前已實際觀察到的資源包種類。
#[derive(Debug, Clone, Copy)]
pub enum Package {
    Data,
    Main,
}

/// 根據官方對照的精確執行檔版本讀取索引。
/// 僅支援已調查的資源版本 1.3.21；其他版本回報未知，不依目錄排序推定。
/// 回傳結果不表示封包已下載、完整性已驗證或索引與二進位清單一致。
pub fn fetch_current(
    platform: crate::version_map::Platform,
    executable: &str,
    package: Package,
) -> Result<BundleIndex, IndexError> {
    let version = crate::version_map::fetch(platform, executable)?;
    let url = observed_index_url(platform, &version, package)?;
    let client = reqwest::blocking::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .map_err(|_| IndexError::RequestFailed)?;
    let index = fetch_with_client(&client, &url)?;
    let expected_name = match package {
        Package::Data => "DataPackage",
        Package::Main => "MainPackage",
    };
    if index.package_name != expected_name {
        return Err(IndexError::IndexInvalidEntry);
    }
    Ok(index)
}

fn observed_index_url(
    platform: crate::version_map::Platform,
    version: &str,
    package: Package,
) -> Result<String, IndexError> {
    if version != "1.3.21" {
        return Err(IndexError::VersionMappingUnknown);
    }
    let platform_dir = match platform {
        crate::version_map::Platform::Windows => "ResourcesPC",
        crate::version_map::Platform::Android => "ResourcesAndroid",
    };
    let package_name = match package {
        Package::Data => "DataPackage",
        Package::Main => "MainPackage",
    };
    Ok(format!("https://wlreftpsrc.chinesegamer.net/WLN/TW/{version}/{platform_dir}/AssetBundle/{package_name}.json"))
}

/// 從固定 HTTPS 位址讀取單一已觀察的索引；拒絕重導向，限制大小及逾時。
/// 本函式為同步操作；呼叫端應在背景工作執行並自行節流。回傳值不代表最新。
pub fn fetch_observed_index() -> Result<BundleIndex, IndexError> {
    let client = reqwest::blocking::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(std::time::Duration::from_secs(20))
        .build()
        .map_err(|_| IndexError::RequestFailed)?;
    fetch_with_client(&client, OBSERVED_INDEX_URL)
}

fn fetch_with_client(
    client: &reqwest::blocking::Client,
    url: &str,
) -> Result<BundleIndex, IndexError> {
    use std::io::Read;
    let response = client
        .get(url)
        .send()
        .map_err(|_| IndexError::RequestFailed)?;
    if response.status() != reqwest::StatusCode::OK {
        return Err(IndexError::UnexpectedResponse);
    }
    if response
        .content_length()
        .is_some_and(|length| length > MAX_BYTES as u64)
    {
        return Err(IndexError::IndexTooLarge);
    }
    let mut body = Vec::new();
    response
        .take(MAX_BYTES as u64 + 1)
        .read_to_end(&mut body)
        .map_err(|_| IndexError::RequestFailed)?;
    parse(&body)
}

/// 解析單份 2.2.5 索引並檢查引用、名稱與資源限制。
/// 成功不表示來源、最新狀態或雜湊演算法已驗證；不得將檔名直接用於檔案操作。
pub fn parse(input: &[u8]) -> Result<BundleIndex, IndexError> {
    if input.len() > MAX_BYTES {
        return Err(IndexError::IndexTooLarge);
    }
    let index: BundleIndex =
        serde_json::from_slice(input).map_err(|_| IndexError::IndexInvalidEntry)?;
    if index.file_version != "2.2.5" {
        return Err(IndexError::IndexUnsupportedVersion);
    }
    if index.bundle_list.len() > MAX_BUNDLES || index.asset_list.len() > MAX_ASSETS {
        return Err(IndexError::IndexTooManyEntries);
    }
    if index.package_name.is_empty()
        || index.package_version.is_empty()
        || index.bundle_list.is_empty()
    {
        return Err(IndexError::IndexInvalidEntry);
    }
    let mut names = BTreeSet::new();
    for bundle in &index.bundle_list {
        let name = &bundle.bundle_name;
        if name.is_empty()
            || name.len() > 200
            || !name
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || b"._-".contains(&c))
            || name == "."
            || name == ".."
            || name.ends_with('.')
            || bundle.file_hash.len() != 32
            || !bundle.file_hash.bytes().all(|c| c.is_ascii_hexdigit())
            || bundle
                .depend_ids
                .iter()
                .any(|&id| id >= index.bundle_list.len())
        {
            return Err(IndexError::IndexInvalidEntry);
        }
        if !names.insert(name.to_ascii_lowercase()) {
            return Err(IndexError::IndexDuplicatePath);
        }
    }
    if index
        .asset_list
        .iter()
        .any(|asset| asset.bundle_id >= index.bundle_list.len() || asset.asset_path.is_empty())
    {
        return Err(IndexError::IndexInvalidEntry);
    }
    Ok(index)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{json, Value};
    fn sample() -> Value {
        json!({"FileVersion":"2.2.5","PackageName":"測試","PackageVersion":"1", "AssetList":[{"Address":"a", "AssetPath":"Assets/a", "AssetGUID":"", "AssetTags":[], "BundleID":0}], "BundleList":[{"BundleName":"safe.bundle", "UnityCRC":0, "FileHash":"0123456789abcdef0123456789abcdef", "FileCRC":"0", "FileSize":5, "Encrypted":false, "Tags":[], "DependIDs":[]}]})
    }
    fn encode(value: &Value) -> Vec<u8> {
        serde_json::to_vec(value).unwrap()
    }
    /// 僅手動或指定驗收工作執行，對固定官方端點發出一次請求。
    #[test]
    #[ignore = "需要連線至官方端點；結果僅反映當時資料"]
    fn official_observed_index_smoke() {
        let index = fetch_observed_index().expect("官方索引讀取或解析失敗");
        assert_eq!(index.file_version, "2.2.5");
        assert!(!index.bundle_list.is_empty());
    }

    #[test]
    fn fetches_synthetic_index_from_local_mock() {
        use std::io::{Read, Write};
        use std::net::TcpListener;
        use std::thread;
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let addr = listener.local_addr().unwrap();
        let body = encode(&sample());
        let server = thread::spawn(move || {
            let (mut socket, _) = listener.accept().unwrap();
            socket
                .set_read_timeout(Some(std::time::Duration::from_secs(3)))
                .unwrap();
            let mut received = Vec::new();
            let mut buffer = [0; 256];
            while !received.ends_with(b"\r\n\r\n") {
                let n = socket.read(&mut buffer).unwrap();
                assert!(n > 0);
                received.extend_from_slice(&buffer[..n]);
            }
            assert!(received.starts_with(b"GET /index HTTP/1.1\r\n"));
            write!(
                socket,
                "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                body.len()
            )
            .unwrap();
            socket.write_all(&body).unwrap();
        });
        let client = reqwest::blocking::Client::builder()
            .no_proxy()
            .redirect(reqwest::redirect::Policy::none())
            .timeout(std::time::Duration::from_secs(3))
            .build()
            .unwrap();
        let result = fetch_with_client(&client, &format!("http://{addr}/index"));
        server.join().unwrap();
        assert_eq!(result.unwrap().bundle_list.len(), 1);
    }

    #[test]
    fn selects_only_observed_platform_and_version_paths() {
        use crate::version_map::Platform;
        assert_eq!(observed_index_url(Platform::Windows,"1.3.21",Package::Main).unwrap(), "https://wlreftpsrc.chinesegamer.net/WLN/TW/1.3.21/ResourcesPC/AssetBundle/MainPackage.json");
        assert!(
            observed_index_url(Platform::Android, "1.3.21", Package::Data)
                .unwrap()
                .contains("/ResourcesAndroid/AssetBundle/DataPackage.json")
        );
        assert_eq!(
            observed_index_url(Platform::Windows, "1.3.22", Package::Data),
            Err(IndexError::VersionMappingUnknown)
        );
        assert_eq!(
            observed_index_url(Platform::Windows, "../evil", Package::Data),
            Err(IndexError::VersionMappingUnknown)
        );
    }

    #[test]
    fn parses_synthetic_index_without_changing_order() {
        let index = parse(&encode(&sample())).unwrap();
        assert_eq!(index.bundle_list[0].bundle_name, "safe.bundle");
        assert_eq!(index.asset_list[0].bundle_id, 0);
        assert!(!index.bundle_list[0].encrypted);
    }
    #[test]
    fn rejects_unknown_version_broken_references_and_paths() {
        let mut value = sample();
        value["FileVersion"] = json!("unknown");
        assert_eq!(
            parse(&encode(&value)).unwrap_err(),
            IndexError::IndexUnsupportedVersion
        );
        let mut value = sample();
        value["AssetList"][0]["BundleID"] = json!(1);
        assert_eq!(
            parse(&encode(&value)).unwrap_err(),
            IndexError::IndexInvalidEntry
        );
        let mut value = sample();
        value["BundleList"][0]["DependIDs"] = json!([1]);
        assert_eq!(
            parse(&encode(&value)).unwrap_err(),
            IndexError::IndexInvalidEntry
        );
        let mut value = sample();
        value["BundleList"][0]["BundleName"] = json!("../evil");
        assert_eq!(
            parse(&encode(&value)).unwrap_err(),
            IndexError::IndexInvalidEntry
        );
    }
    #[test]
    fn rejects_duplicate_names_invalid_hash_and_oversize() {
        let mut value = sample();
        let mut duplicate = value["BundleList"][0].clone();
        duplicate["BundleName"] = json!("SAFE.BUNDLE");
        value["BundleList"].as_array_mut().unwrap().push(duplicate);
        assert_eq!(
            parse(&encode(&value)).unwrap_err(),
            IndexError::IndexDuplicatePath
        );
        let mut value = sample();
        value["BundleList"][0]["FileHash"] = json!("not-a-hash");
        assert_eq!(
            parse(&encode(&value)).unwrap_err(),
            IndexError::IndexInvalidEntry
        );
        assert_eq!(
            parse(&vec![b' '; MAX_BYTES + 1]).unwrap_err(),
            IndexError::IndexTooLarge
        );
    }
}
