//! 共用核心結構化事件及錯誤碼；不接受自由文字或敏感資料。

use serde::Serialize;
use std::io::{self, Write};

/// 跨模組共用的穩定錯誤碼；新增代碼時不得重新賦予既有代碼其他意義。
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ErrorCode {
    InvalidPath,
    DuplicatePath,
    StorageFailure,
    InvalidValidator,
    RequestFailed,
    UnexpectedResponse,
    IndexTooLarge,
    IndexInvalidEncoding,
    IndexInvalidEntry,
    IndexDuplicatePath,
    IndexTooManyEntries,
    IndexUnsupportedVersion,
    CacheInvalidInput,
    CacheIntegrityFailure,
    CacheTooLarge,
    VersionMappingUnknown,
    VersionMappingAmbiguous,
    SnapshotChanged,
    DependencyCycle,
    ResourceNotFound,
    UnsupportedEncryption,
    DownloadQuotaExceeded,
    TrustedDigestMissing,
    ScheduleInvalid,
    ExtractionInvalid,
    ExtractionLimitExceeded,
    UpdateCancelled,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum EventKind {
    ResourceUpdateProgress,
}

/// 固定欄位的日誌事件；不包含路徑、帳密、封包及自由文字。
#[derive(Debug, Serialize)]
pub struct Event {
    pub schema_version: u8,
    pub event: EventKind,
    pub completed: u64,
    pub total: u64,
    pub error: Option<ErrorCode>,
}

impl Event {
    /// 建立資源更新進度事件；呼叫端須確保計數與更新工作一致。
    pub fn resource_update_progress(completed: u64, total: u64, error: Option<ErrorCode>) -> Self {
        Self {
            schema_version: 1,
            event: EventKind::ResourceUpdateProgress,
            completed,
            total,
            error,
        }
    }
}

/// 將單一事件寫為一行 JSON；寫入失敗時回傳錯誤，輸出可能已經部分寫入。
/// 多執行緒呼叫端須自行序列化寫入並管理輸出生命週期。
pub fn write_json_line(writer: &mut impl Write, event: &Event) -> io::Result<()> {
    let data = serde_json::to_vec(event).map_err(io::Error::other)?;
    writer.write_all(&data)?;
    writer.write_all(b"\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn writes_one_structured_line_without_free_text() {
        let mut bytes = Vec::new();
        write_json_line(
            &mut bytes,
            &Event::resource_update_progress(1, 3, Some(ErrorCode::StorageFailure)),
        )
        .unwrap();
        assert_eq!(bytes.iter().filter(|&&b| b == b'\n').count(), 1);
        let value: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(
            value,
            serde_json::json!({"schema_version": 1, "event": "RESOURCE_UPDATE_PROGRESS", "completed": 1, "total": 3, "error": "STORAGE_FAILURE"})
        );
    }

    #[test]
    fn writes_null_when_there_is_no_error() {
        let mut bytes = Vec::new();
        write_json_line(&mut bytes, &Event::resource_update_progress(0, 0, None)).unwrap();
        let value: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert!(value["error"].is_null());
    }

    #[test]
    fn propagates_writer_failure() {
        struct FailingWriter;
        impl Write for FailingWriter {
            fn write(&mut self, _: &[u8]) -> io::Result<usize> {
                Err(io::Error::new(io::ErrorKind::BrokenPipe, "closed"))
            }
            fn flush(&mut self) -> io::Result<()> {
                Ok(())
            }
        }
        assert_eq!(
            write_json_line(
                &mut FailingWriter,
                &Event::resource_update_progress(0, 1, None)
            )
            .unwrap_err()
            .kind(),
            io::ErrorKind::BrokenPipe
        );
    }
}
