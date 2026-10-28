//! 在受限記憶體中讀取 UnityFS 容器項目，不自動寫檔或解析遊戲物件。
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use unity_bundle_assets::{Bundle, Limits};
pub use wlre_core_observability::ErrorCode as ExtractError;
const MAX_INPUT: usize = 64 * 1024 * 1024;
const MAX_OUTPUT: usize = 32 * 1024 * 1024;
const MAX_ENTRIES: usize = 1024;

#[derive(Debug, Eq, PartialEq)]
pub struct Entry {
    pub name: String,
    pub data: Vec<u8>,
}

/// 僅接收可信 SHA-256 相符的未加密 UnityFS；限制輸入、解壓大小和項目數。
/// 此函式不寫入檔案、不解析內含的 Unity 物件；呼叫端須妥善保護回傳的遊戲資料。
/// 不得用同次下載自己計算的摘要假裝可信來源；不支援加密或未知格式。
pub fn extract(input: &[u8], expected_sha256: &str) -> Result<Vec<Entry>, ExtractError> {
    if input.len() > MAX_INPUT {
        return Err(ExtractError::ExtractionLimitExceeded);
    }
    let expected = crate::verified_cache::validate_digest(expected_sha256)?;
    if format!("{:x}", Sha256::digest(input)) != expected {
        return Err(ExtractError::CacheIntegrityFailure);
    }
    if !input.starts_with(b"UnityFS\0") {
        return Err(ExtractError::ExtractionInvalid);
    }
    let limits = Limits::default()
        .with_max_file_size(MAX_INPUT as u64)
        .with_max_decompressed(MAX_OUTPUT as u64)
        .with_max_objects(MAX_ENTRIES as u64);
    let bundle = Bundle::parse_with(input, limits).map_err(|_| ExtractError::ExtractionInvalid)?;
    if bundle.entries().len() > MAX_ENTRIES {
        return Err(ExtractError::ExtractionLimitExceeded);
    }
    let mut seen = BTreeSet::new();
    let mut total = 0usize;
    let mut result = Vec::new();
    for item in bundle.entries() {
        let name = item.path();
        if name.is_empty()
            || name.len() > 200
            || name.ends_with('.')
            || !name
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
            || name == "."
            || name == ".."
        {
            return Err(ExtractError::ExtractionInvalid);
        }
        let stem = name.split('.').next().unwrap_or("").to_ascii_uppercase();
        if matches!(
            stem.as_str(),
            "CON"
                | "PRN"
                | "AUX"
                | "NUL"
                | "COM1"
                | "COM2"
                | "COM3"
                | "COM4"
                | "COM5"
                | "COM6"
                | "COM7"
                | "COM8"
                | "COM9"
                | "LPT1"
                | "LPT2"
                | "LPT3"
                | "LPT4"
                | "LPT5"
                | "LPT6"
                | "LPT7"
                | "LPT8"
                | "LPT9"
        ) || !seen.insert(name.to_ascii_lowercase())
        {
            return Err(ExtractError::ExtractionInvalid);
        }
        let bytes = bundle.bytes(item).ok_or(ExtractError::ExtractionInvalid)?;
        total = total
            .checked_add(bytes.len())
            .ok_or(ExtractError::ExtractionLimitExceeded)?;
        if total > MAX_OUTPUT {
            return Err(ExtractError::ExtractionLimitExceeded);
        }
        result.push(Entry {
            name: name.to_owned(),
            data: bytes.to_vec(),
        });
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn sha(bytes: &[u8]) -> String {
        format!("{:x}", Sha256::digest(bytes))
    }
    // 自製無壓縮 UnityFS，沒有遊戲資料。
    fn synthetic(name: &str) -> Vec<u8> {
        let data = b"sample";
        let mut info = vec![0u8; 16];
        info.extend_from_slice(&1i32.to_be_bytes());
        info.extend_from_slice(&(data.len() as u32).to_be_bytes());
        info.extend_from_slice(&(data.len() as u32).to_be_bytes());
        info.extend_from_slice(&0u16.to_be_bytes());
        info.extend_from_slice(&1i32.to_be_bytes());
        info.extend_from_slice(&0i64.to_be_bytes());
        info.extend_from_slice(&(data.len() as i64).to_be_bytes());
        info.extend_from_slice(&0u32.to_be_bytes());
        info.extend_from_slice(name.as_bytes());
        info.push(0);
        let mut out = b"UnityFS\0".to_vec();
        out.extend_from_slice(&6u32.to_be_bytes());
        out.extend_from_slice(b"5.x.x\0");
        out.extend_from_slice(b"2019.4.0f1\0");
        let offset = out.len();
        out.extend_from_slice(&0i64.to_be_bytes());
        out.extend_from_slice(&(info.len() as u32).to_be_bytes());
        out.extend_from_slice(&(info.len() as u32).to_be_bytes());
        out.extend_from_slice(&0x40u32.to_be_bytes());
        out.extend_from_slice(&info);
        out.extend_from_slice(data);
        let size = out.len() as i64;
        out[offset..offset + 8].copy_from_slice(&size.to_be_bytes());
        out
    }
    /// 唯讀格式驗證；摘要由同一回應計算，只驗證解析相容性，不證明來源完整性。
    #[test]
    #[ignore = "需取得一份官方已觀察的未加密封包"]
    fn official_unity_container_smoke() {
        use std::io::Read;
        let client = reqwest::blocking::Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .timeout(std::time::Duration::from_secs(20))
            .build()
            .unwrap();
        let response=client.get("https://wlreftpsrc.chinesegamer.net/WLN/TW/1.3.21/ResourcesPC/AssetBundle/datapackage_data_v.bundle").send().unwrap();
        assert_eq!(response.status(), reqwest::StatusCode::OK);
        let mut bytes = Vec::new();
        response.take(65537).read_to_end(&mut bytes).unwrap();
        assert!(bytes.len() <= 65536);
        let entries = extract(&bytes, &sha(&bytes)).unwrap();
        assert!(!entries.is_empty());
    }

    #[test]
    fn extracts_synthetic_container_in_memory() {
        let bytes = synthetic("CAB-test");
        let entries = extract(&bytes, &sha(&bytes)).unwrap();
        assert_eq!(
            entries,
            vec![Entry {
                name: "CAB-test".into(),
                data: b"sample".to_vec()
            }]
        );
    }
    #[test]
    fn rejects_wrong_hash_and_unsafe_names() {
        let bytes = synthetic("../escape");
        assert_eq!(
            extract(&bytes, &"0".repeat(64)),
            Err(ExtractError::CacheIntegrityFailure)
        );
        assert_eq!(
            extract(&bytes, &sha(&bytes)),
            Err(ExtractError::ExtractionInvalid)
        );
        let bytes = synthetic("CON.txt");
        assert_eq!(
            extract(&bytes, &sha(&bytes)),
            Err(ExtractError::ExtractionInvalid)
        );
        let invalid = b"not unity";
        assert_eq!(
            extract(invalid, &sha(invalid)),
            Err(ExtractError::ExtractionInvalid)
        );
    }
}
