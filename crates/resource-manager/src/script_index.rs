//! 腳本路徑清單的受限解析；不推論更新完整性或驗證碼演算法。

use crate::ResourcePath;
use std::collections::BTreeSet;

const MAX_BYTES: usize = 1_048_576;
const MAX_ENTRIES: usize = 20_000;
const MAX_PATH_BYTES: usize = 512;

#[derive(Debug, Eq, PartialEq)]
pub struct ScriptIndexEntry {
    pub path: ResourcePath,
    /// 原始識別值，尚未作為完整性雜湊使用。
    pub identifier: String,
}

pub use wlre_core_observability::ErrorCode as ScriptIndexError;

/// 解析觀察到的 `Lua/相對路徑|32位十六進位識別值` 格式。
/// 不驗證官方版本、檔案完整性、資料來源或索引是否完整；空白清單拒絕。
/// 限制大小與筆數，遇到無效列或重複路徑時整份清單失敗。
pub fn parse(input: &[u8]) -> Result<Vec<ScriptIndexEntry>, ScriptIndexError> {
    if input.len() > MAX_BYTES {
        return Err(ScriptIndexError::IndexTooLarge);
    }
    let text = std::str::from_utf8(input).map_err(|_| ScriptIndexError::IndexInvalidEncoding)?;
    let text = text.strip_prefix('\u{feff}').unwrap_or(text);
    let mut entries = Vec::new();
    let mut seen = BTreeSet::new();
    for line in text.lines() {
        if entries.len() >= MAX_ENTRIES {
            return Err(ScriptIndexError::IndexTooManyEntries);
        }
        let (path, identifier) = line
            .split_once('|')
            .ok_or(ScriptIndexError::IndexInvalidEntry)?;
        if !path.starts_with("Lua/")
            || path.len() > MAX_PATH_BYTES
            || !path.is_ascii()
            || identifier.len() != 32
            || !identifier.bytes().all(|b| b.is_ascii_hexdigit())
        {
            return Err(ScriptIndexError::IndexInvalidEntry);
        }
        let path = ResourcePath::new(path).map_err(|_| ScriptIndexError::IndexInvalidEntry)?;
        // 不允許 Windows 不區分大小寫時發生重複路徑。
        if !seen.insert(path.as_str().to_ascii_lowercase()) {
            return Err(ScriptIndexError::IndexDuplicatePath);
        }
        entries.push(ScriptIndexEntry {
            path,
            identifier: identifier.to_ascii_uppercase(),
        });
    }
    if entries.is_empty() {
        return Err(ScriptIndexError::IndexInvalidEntry);
    }
    Ok(entries)
}

#[cfg(test)]
mod tests {
    use super::*;
    const ID: &str = "0123456789abcdef0123456789abcdef";

    #[test]
    fn parses_synthetic_entries_and_normalizes_identifier() {
        let input = format!("Lua/a.lua|{ID}\r\nLua/dir/b.lua|{ID}\n");
        let entries = parse(input.as_bytes()).unwrap();
        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0].path.as_str(), "Lua/a.lua");
        assert_eq!(entries[0].identifier, ID.to_ascii_uppercase());
    }

    #[test]
    fn rejects_invalid_and_colliding_entries() {
        for input in [
            "",
            "Lua/../x|0123456789abcdef0123456789abcdef",
            "Other/a|0123456789abcdef0123456789abcdef",
            "Lua/a|not-a-hash",
            "Lua/a|0123456789abcdef0123456789abcdef|extra",
        ] {
            assert_eq!(
                parse(input.as_bytes()),
                Err(ScriptIndexError::IndexInvalidEntry)
            );
        }
        let duplicate = format!("Lua/A|{ID}\nLua/a|{ID}\n");
        assert_eq!(
            parse(duplicate.as_bytes()),
            Err(ScriptIndexError::IndexDuplicatePath)
        );
        assert_eq!(parse(&[0xff]), Err(ScriptIndexError::IndexInvalidEncoding));
        assert_eq!(
            parse(&vec![b'a'; MAX_BYTES + 1]),
            Err(ScriptIndexError::IndexTooLarge)
        );
    }

    #[test]
    fn rejects_entry_limit_without_partial_results() {
        let input: String = (0..=MAX_ENTRIES)
            .map(|i| format!("Lua/{i}|{ID}\n"))
            .collect();
        assert_eq!(
            parse(input.as_bytes()),
            Err(ScriptIndexError::IndexTooManyEntries)
        );
    }
}
