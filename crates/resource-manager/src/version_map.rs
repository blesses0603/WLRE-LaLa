//! 解析官方觀察到的執行檔版本對照；不推論未知版本。

use serde::Deserialize;
use std::collections::BTreeMap;
pub use wlre_core_observability::ErrorCode as VersionError;

const MAX_BYTES: usize = 16 * 1024;

/// 僅提供實際觀察過的來源；macOS 來源尚未確認。
#[derive(Debug, Clone, Copy)]
pub enum Platform {
    Windows,
    Android,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Mapping {
    #[serde(rename = "ExeVer")]
    executable: String,
    #[serde(rename = "DataVer")]
    data: String,
}

/// 下載指定平台固定的版本對照，並只選取精確執行檔版本。
/// 同步操作，呼叫端須負責背景執行與節流；不代表資源已下載或驗證。
pub fn fetch(platform: Platform, executable: &str) -> Result<String, VersionError> {
    let url = match platform {
        Platform::Windows => "https://wlreftpsrc.chinesegamer.net/WLN/TW/ResourcePath_PC.dat",
        Platform::Android => "https://wlreftpsrc.chinesegamer.net/WLN/TW/ResourcePath_ANDROID.dat",
    };
    let client = reqwest::blocking::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|_| VersionError::RequestFailed)?;
    let response = client
        .get(url)
        .send()
        .map_err(|_| VersionError::RequestFailed)?;
    if response.status() != reqwest::StatusCode::OK {
        return Err(VersionError::UnexpectedResponse);
    }
    if response
        .content_length()
        .is_some_and(|n| n > MAX_BYTES as u64)
    {
        return Err(VersionError::IndexTooLarge);
    }
    let mut bytes = Vec::new();
    std::io::Read::read_to_end(
        &mut std::io::Read::take(response, MAX_BYTES as u64 + 1),
        &mut bytes,
    )
    .map_err(|_| VersionError::RequestFailed)?;
    select(&bytes, executable)
}

pub(crate) fn valid_version(value: &str) -> bool {
    value.len() <= 32
        && value.split('.').count() == 3
        && value
            .split('.')
            .all(|v| !v.is_empty() && v.bytes().all(|b| b.is_ascii_digit()))
}

/// 解析官方觀察到的陣列尾隨逗號格式；只容許陣列結尾的單一尾隨逗號。
/// 重複執行檔版本及未列出的版本都不推定結果。輸入不得超過 16 KiB。
pub fn select(bytes: &[u8], executable: &str) -> Result<String, VersionError> {
    if bytes.len() > MAX_BYTES {
        return Err(VersionError::IndexTooLarge);
    }
    if !valid_version(executable) {
        return Err(VersionError::IndexInvalidEntry);
    }
    let versions = parse_mapping(bytes)?;
    versions
        .get(executable)
        .cloned()
        .ok_or(VersionError::VersionMappingUnknown)
}

fn parse_mapping(bytes: &[u8]) -> Result<BTreeMap<String, String>, VersionError> {
    if bytes.len() > MAX_BYTES {
        return Err(VersionError::IndexTooLarge);
    }
    let text = std::str::from_utf8(bytes).map_err(|_| VersionError::IndexInvalidEncoding)?;
    let mut trimmed = text.trim_end().to_owned();
    if trimmed.ends_with(']') {
        let before = trimmed[..trimmed.len() - 1].trim_end();
        if let Some(prefix) = before.strip_suffix(',') {
            if !prefix.trim_end().ends_with('}') {
                return Err(VersionError::IndexInvalidEntry);
            }
            trimmed = format!("{}]", prefix);
        }
    }
    let entries: Vec<Mapping> =
        serde_json::from_str(&trimmed).map_err(|_| VersionError::IndexInvalidEntry)?;
    if entries.is_empty() {
        return Err(VersionError::IndexInvalidEntry);
    }
    let mut versions = BTreeMap::new();
    for entry in entries {
        if !valid_version(&entry.executable) || !valid_version(&entry.data) {
            return Err(VersionError::IndexInvalidEntry);
        }
        if versions.insert(entry.executable, entry.data).is_some() {
            return Err(VersionError::VersionMappingAmbiguous);
        }
    }
    Ok(versions)
}

/// 從官方對照中，以三段數字比較選擇最高的 ExeVer 及其對應 DataVer。
/// 這是專案的選擇政策，不代表已證明官方啟動器內部採用相同規則。
/// 版本數字不受支援或出現數值相同的不同表示時拒絕；不根據資料夾排序。
pub fn select_latest(bytes: &[u8]) -> Result<(String, String), VersionError> {
    let versions = parse_mapping(bytes)?;
    let mut best: Option<([u32; 3], String, String)> = None;
    let mut seen = std::collections::BTreeSet::new();
    for (exe, data) in versions {
        let mut parts = exe.split('.');
        let parse = |part: Option<&str>| -> Result<u32, VersionError> {
            part.ok_or(VersionError::IndexInvalidEntry)?
                .parse()
                .map_err(|_| VersionError::IndexInvalidEntry)
        };
        let key = [
            parse(parts.next())?,
            parse(parts.next())?,
            parse(parts.next())?,
        ];
        if !seen.insert(key) {
            return Err(VersionError::VersionMappingAmbiguous);
        }
        if let Some((old, _, _)) = &best {
            if &key == old {
                return Err(VersionError::VersionMappingAmbiguous);
            }
            if &key < old {
                continue;
            }
        }
        best = Some((key, exe, data));
    }
    best.map(|(_, exe, data)| (exe, data))
        .ok_or(VersionError::VersionMappingUnknown)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn selects_exact_version_in_observed_trailing_comma_format() {
        let data =
            br#"[{"ExeVer":"1.2.0","DataVer":"1.3.21"},{"ExeVer":"1.3.0","DataVer":"1.3.22"},]"#;
        assert_eq!(select(data, "1.2.0"), Ok("1.3.21".into()));
        assert_eq!(
            select(data, "1.2.1"),
            Err(VersionError::VersionMappingUnknown)
        );
    }
    #[test]
    fn chooses_highest_announced_executable_numerically() {
        let data =
            br#"[{"ExeVer":"1.9.0","DataVer":"1.3.21"},{"ExeVer":"1.10.0","DataVer":"1.3.22"},]"#;
        assert_eq!(select_latest(data), Ok(("1.10.0".into(), "1.3.22".into())));
        let duplicate =
            br#"[{"ExeVer":"1.01.0","DataVer":"1.3.21"},{"ExeVer":"1.1.0","DataVer":"1.3.22"}]"#;
        assert_eq!(
            select_latest(duplicate),
            Err(VersionError::VersionMappingAmbiguous)
        );
    }

    #[test]
    fn rejects_ambiguous_or_unsafe_mappings() {
        let dup =
            br#"[{"ExeVer":"1.2.0","DataVer":"1.3.21"},{"ExeVer":"1.2.0","DataVer":"1.3.22"}]"#;
        assert_eq!(
            select(dup, "1.2.0"),
            Err(VersionError::VersionMappingAmbiguous)
        );
        for data in [
            br#"[{"ExeVer":"1.2.0","DataVer":"../evil"}]"#.as_slice(),
            br#"[,]"#,
            br#"[]"#,
        ] {
            assert_eq!(select(data, "1.2.0"), Err(VersionError::IndexInvalidEntry));
        }
        assert_eq!(
            select(b"[]", "../evil"),
            Err(VersionError::IndexInvalidEntry)
        );
        assert_eq!(
            select(&vec![0; MAX_BYTES + 1], "1.2.0"),
            Err(VersionError::IndexTooLarge)
        );
    }
}
