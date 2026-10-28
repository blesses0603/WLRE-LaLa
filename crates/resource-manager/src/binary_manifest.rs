//! 已觀察的 YooAsset 2.2.5 二進位清單；CRC 用於偵測損毀而非防竄改。

use crate::bundle_index::{self, Asset, Bundle, BundleIndex};
pub use wlre_core_observability::ErrorCode as ManifestError;

const MAX_BYTES: usize = 16 * 1024 * 1024;
const MAX_ASSETS: usize = 500_000;
const MAX_BUNDLES: usize = 100_000;

struct Reader<'a> {
    bytes: &'a [u8],
    pos: usize,
}
impl<'a> Reader<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8], ManifestError> {
        let end = self
            .pos
            .checked_add(n)
            .ok_or(ManifestError::IndexInvalidEntry)?;
        let result = self
            .bytes
            .get(self.pos..end)
            .ok_or(ManifestError::IndexInvalidEntry)?;
        self.pos = end;
        Ok(result)
    }
    fn u16(&mut self) -> Result<u16, ManifestError> {
        Ok(u16::from_le_bytes(
            self.take(2)?
                .try_into()
                .map_err(|_| ManifestError::IndexInvalidEntry)?,
        ))
    }
    fn u32(&mut self) -> Result<u32, ManifestError> {
        Ok(u32::from_le_bytes(
            self.take(4)?
                .try_into()
                .map_err(|_| ManifestError::IndexInvalidEntry)?,
        ))
    }
    fn i32(&mut self) -> Result<i32, ManifestError> {
        Ok(i32::from_le_bytes(
            self.take(4)?
                .try_into()
                .map_err(|_| ManifestError::IndexInvalidEntry)?,
        ))
    }
    fn size(&mut self) -> Result<u64, ManifestError> {
        let value = i64::from_le_bytes(
            self.take(8)?
                .try_into()
                .map_err(|_| ManifestError::IndexInvalidEntry)?,
        );
        u64::try_from(value).map_err(|_| ManifestError::IndexInvalidEntry)
    }
    fn boolean(&mut self) -> Result<bool, ManifestError> {
        match self.take(1)?[0] {
            0 => Ok(false),
            1 => Ok(true),
            _ => Err(ManifestError::IndexInvalidEntry),
        }
    }
    fn string(&mut self) -> Result<String, ManifestError> {
        let len = self.u16()? as usize;
        Ok(std::str::from_utf8(self.take(len)?)
            .map_err(|_| ManifestError::IndexInvalidEncoding)?
            .to_owned())
    }
    fn strings(&mut self) -> Result<Vec<String>, ManifestError> {
        let n = self.u16()?;
        (0..n).map(|_| self.string()).collect()
    }
    fn ids(&mut self) -> Result<Vec<usize>, ManifestError> {
        let n = self.u16()?;
        (0..n)
            .map(|_| usize::try_from(self.i32()?).map_err(|_| ManifestError::IndexInvalidEntry))
            .collect()
    }
    fn count(&mut self, max: usize) -> Result<usize, ManifestError> {
        let n = usize::try_from(self.i32()?).map_err(|_| ManifestError::IndexInvalidEntry)?;
        if n > max {
            return Err(ManifestError::IndexTooManyEntries);
        }
        Ok(n)
    }
}

/// 驗證小端 CRC32，並解析 2.2.5 格式及確認套件名稱、完整版本與參照。
/// CRC32 是損毀檢查，並不能認證來源或防止惡意竄改；呼叫端須自行確認來源。
/// 不提取遊戲資源，也不保證完整索引是目前版本。
pub fn parse(
    bytes: &[u8],
    hash_text: &str,
    package: &str,
    version: &str,
) -> Result<BundleIndex, ManifestError> {
    if bytes.len() > MAX_BYTES {
        return Err(ManifestError::IndexTooLarge);
    }
    if hash_text.len() != 8 || !hash_text.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err(ManifestError::IndexInvalidEntry);
    }
    let actual: String = crc32fast::hash(bytes)
        .to_le_bytes()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect();
    if !actual.eq_ignore_ascii_case(hash_text) {
        return Err(ManifestError::CacheIntegrityFailure);
    }
    let mut reader = Reader { bytes, pos: 0 };
    if reader.u32()? != 0x00594f4f {
        return Err(ManifestError::IndexInvalidEntry);
    }
    let file_version = reader.string()?;
    if file_version != "2.2.5" {
        return Err(ManifestError::IndexUnsupportedVersion);
    }
    reader.boolean()?;
    reader.boolean()?;
    reader.boolean()?;
    let output_style = reader.i32()?;
    reader.i32()?;
    reader.string()?;
    let package_name = reader.string()?;
    let package_version = reader.string()?;
    reader.string()?;
    if output_style != 1 || package_name != package || package_version != version {
        return Err(ManifestError::IndexInvalidEntry);
    }
    let asset_count = reader.count(MAX_ASSETS)?;
    let mut asset_list = Vec::with_capacity(asset_count.min(4096));
    for _ in 0..asset_count {
        let address = reader.string()?;
        let asset_path = reader.string()?;
        let asset_guid = reader.string()?;
        let asset_tags = reader.strings()?;
        let bundle_id =
            usize::try_from(reader.i32()?).map_err(|_| ManifestError::IndexInvalidEntry)?;
        asset_list.push(Asset {
            address,
            asset_path,
            asset_guid,
            asset_tags,
            bundle_id,
        });
    }
    let bundle_count = reader.count(MAX_BUNDLES)?;
    let mut bundle_list = Vec::with_capacity(bundle_count.min(4096));
    for _ in 0..bundle_count {
        let bundle_name = reader.string()?;
        let unity_crc = reader.u32()?;
        let file_hash = reader.string()?;
        let file_crc = reader.string()?;
        let file_size = reader.size()?;
        let encrypted = reader.boolean()?;
        let tags = reader.strings()?;
        let depend_ids = reader.ids()?;
        bundle_list.push(Bundle {
            bundle_name,
            unity_crc,
            file_hash,
            file_crc,
            file_size,
            encrypted,
            tags,
            depend_ids,
        });
    }
    if reader.pos != bytes.len() {
        return Err(ManifestError::IndexInvalidEntry);
    }
    bundle_index::validate(BundleIndex {
        file_version,
        package_name,
        package_version,
        asset_list,
        bundle_list,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn string(out: &mut Vec<u8>, s: &str) {
        out.extend_from_slice(&(s.len() as u16).to_le_bytes());
        out.extend_from_slice(s.as_bytes());
    }
    fn sample() -> Vec<u8> {
        let mut b = Vec::new();
        b.extend_from_slice(&0x00594f4fu32.to_le_bytes());
        string(&mut b, "2.2.5");
        b.extend_from_slice(&[0, 0, 0]);
        b.extend_from_slice(&1i32.to_le_bytes());
        b.extend_from_slice(&0i32.to_le_bytes());
        string(&mut b, "pipeline");
        string(&mut b, "DataPackage");
        string(&mut b, "revision");
        string(&mut b, "");
        b.extend_from_slice(&1i32.to_le_bytes());
        string(&mut b, "address");
        string(&mut b, "Assets/a");
        string(&mut b, "");
        b.extend_from_slice(&0u16.to_le_bytes());
        b.extend_from_slice(&0i32.to_le_bytes());
        b.extend_from_slice(&1i32.to_le_bytes());
        string(&mut b, "a.bundle");
        b.extend_from_slice(&0u32.to_le_bytes());
        string(&mut b, "0123456789abcdef0123456789abcdef");
        string(&mut b, "00000000");
        b.extend_from_slice(&5i64.to_le_bytes());
        b.push(0);
        b.extend_from_slice(&0u16.to_le_bytes());
        b.extend_from_slice(&0u16.to_le_bytes());
        b
    }
    fn crc(b: &[u8]) -> String {
        crc32fast::hash(b)
            .to_le_bytes()
            .iter()
            .map(|x| format!("{x:02x}"))
            .collect()
    }
    #[test]
    #[ignore = "需對官方固定端點執行低負載驗證"]
    fn official_binary_manifest_smoke() {
        use std::io::Read;
        let client = reqwest::blocking::Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .timeout(std::time::Duration::from_secs(20))
            .build()
            .unwrap();
        let base =
            "https://wlreftpsrc.chinesegamer.net/WLN/TW/1.3.21/ResourcesPC/AssetBundle/DataPackage";
        let read = |ext: &str, limit: u64| {
            let response = client.get(format!("{base}.{ext}")).send().unwrap();
            assert_eq!(response.status(), reqwest::StatusCode::OK);
            let mut bytes = Vec::new();
            response.take(limit + 1).read_to_end(&mut bytes).unwrap();
            assert!(bytes.len() as u64 <= limit);
            bytes
        };
        let version = String::from_utf8(read("version", 256)).unwrap();
        let hash = String::from_utf8(read("hash", 8)).unwrap();
        let data = read("bytes", MAX_BYTES as u64);
        let index = parse(&data, hash.trim(), "DataPackage", version.trim()).unwrap();
        assert!(!index.bundle_list.is_empty());
    }

    #[test]
    fn parses_synthetic_checked_manifest() {
        let b = sample();
        let index = parse(&b, &crc(&b), "DataPackage", "revision").unwrap();
        assert_eq!(index.asset_list[0].bundle_id, 0);
        assert_eq!(index.bundle_list[0].bundle_name, "a.bundle");
    }
    #[test]
    fn rejects_corruption_wrong_identity_truncation_and_trailing_data() {
        let b = sample();
        assert_eq!(
            parse(&b, "00000000", "DataPackage", "revision").unwrap_err(),
            ManifestError::CacheIntegrityFailure
        );
        assert_eq!(
            parse(&b, &crc(&b), "MainPackage", "revision").unwrap_err(),
            ManifestError::IndexInvalidEntry
        );
        let truncated = &b[..b.len() - 1];
        assert_eq!(
            parse(truncated, &crc(truncated), "DataPackage", "revision").unwrap_err(),
            ManifestError::IndexInvalidEntry
        );
        let mut extra = b;
        extra.push(0);
        assert_eq!(
            parse(&extra, &crc(&extra), "DataPackage", "revision").unwrap_err(),
            ManifestError::IndexInvalidEntry
        );
    }
}
