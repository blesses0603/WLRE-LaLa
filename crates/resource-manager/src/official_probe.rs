//! 只觀察已確認存在的單一官方檔案，不判定整體資源版本。

use reqwest::blocking::Client;
use reqwest::header::{ETAG, IF_NONE_MATCH};
use reqwest::{redirect::Policy, StatusCode};
use std::time::Duration;

const OBSERVED_URL: &str = "https://wlreftpsrc.chinesegamer.net/WLN/TW/DownloadUrl_PC.txt";

/// 單一檔案的觀察結果，與遊戲資源是否最新無關。
#[derive(Debug, Eq, PartialEq)]
pub enum Observation {
    Unchanged,
    ValidatorChanged { etag: String },
    Unknown { etag: Option<String> },
}

pub use wlre_core_observability::ErrorCode as ProbeError;

/// 對固定的官方 HTTPS 端點執行一次 HEAD。禁止重導向，不下載內容。
/// 呼叫端負責節流與保存此檔案自身的 ETag；不得跨檔案使用。
/// 超時、網路或非預期回應皆回傳錯誤，不代表檔案沒有變更。
pub fn probe(previous_etag: Option<&str>) -> Result<Observation, ProbeError> {
    let client = Client::builder()
        .redirect(Policy::none())
        .timeout(Duration::from_secs(10))
        .build()
        .map_err(|_| ProbeError::RequestFailed)?;
    probe_with_client(&client, OBSERVED_URL, previous_etag)
}

fn probe_with_client(
    client: &Client,
    url: &str,
    previous_etag: Option<&str>,
) -> Result<Observation, ProbeError> {
    let previous = previous_etag.map(valid_etag).transpose()?;
    let mut request = client.head(url);
    if let Some(etag) = previous {
        request = request.header(IF_NONE_MATCH, etag);
    }
    let response = request.send().map_err(|_| ProbeError::RequestFailed)?;
    let etag = response.headers().get(ETAG).and_then(|v| v.to_str().ok());
    classify(response.status(), previous, etag)
}

fn valid_etag(value: &str) -> Result<&str, ProbeError> {
    let opaque = value.strip_prefix("W/").unwrap_or(value);
    if opaque.len() < 2
        || !opaque.starts_with('"')
        || !opaque.ends_with('"')
        || opaque[1..opaque.len() - 1]
            .bytes()
            .any(|b| !(b == 0x21 || (0x23..=0x7e).contains(&b)))
    {
        return Err(ProbeError::InvalidValidator);
    }
    Ok(value)
}

fn classify(
    status: StatusCode,
    previous: Option<&str>,
    response_etag: Option<&str>,
) -> Result<Observation, ProbeError> {
    if status == StatusCode::NOT_MODIFIED {
        return if previous.is_some() {
            Ok(Observation::Unchanged)
        } else {
            Err(ProbeError::UnexpectedResponse)
        };
    }
    if status != StatusCode::OK {
        return Err(ProbeError::UnexpectedResponse);
    }
    let etag = response_etag.and_then(|value| valid_etag(value).ok());
    match (previous, etag) {
        (Some(old), Some(new)) if old != new => Ok(Observation::ValidatorChanged {
            etag: new.to_owned(),
        }),
        (_, current) => Ok(Observation::Unknown {
            etag: current.map(str::to_owned),
        }),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sends_head_and_conditional_validator_to_mock_server() {
        use std::io::{Read, Write};
        use std::net::TcpListener;
        use std::thread;

        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let server = thread::spawn(move || {
            let (mut socket, _) = listener.accept().unwrap();
            socket
                .set_read_timeout(Some(Duration::from_secs(3)))
                .unwrap();
            let mut request = Vec::new();
            let mut buffer = [0; 256];
            while !request.ends_with(b"\r\n\r\n") {
                let size = socket.read(&mut buffer).unwrap();
                assert!(size > 0);
                request.extend_from_slice(&buffer[..size]);
            }
            let request = String::from_utf8(request).unwrap().to_ascii_lowercase();
            assert!(request.starts_with("head /test http/1.1\r\n"));
            assert!(request.contains("if-none-match: \"old\"\r\n"));
            socket
                .write_all(b"HTTP/1.1 304 Not Modified\r\nConnection: close\r\n\r\n")
                .unwrap();
        });
        let client = Client::builder()
            .no_proxy()
            .redirect(Policy::none())
            .timeout(Duration::from_secs(3))
            .build()
            .unwrap();
        let result = probe_with_client(&client, &format!("http://{address}/test"), Some("\"old\""));
        server.join().unwrap();
        assert_eq!(result, Ok(Observation::Unchanged));
    }

    #[test]
    fn classifies_conditional_response_without_claiming_global_freshness() {
        assert_eq!(
            classify(StatusCode::NOT_MODIFIED, Some("\"old\""), None),
            Ok(Observation::Unchanged)
        );
        assert_eq!(
            classify(StatusCode::OK, Some("\"old\""), Some("\"new\"")),
            Ok(Observation::ValidatorChanged {
                etag: "\"new\"".into()
            })
        );
        assert_eq!(
            classify(StatusCode::OK, None, Some("\"new\"")),
            Ok(Observation::Unknown {
                etag: Some("\"new\"".into())
            })
        );
        assert_eq!(
            classify(StatusCode::OK, Some("\"old\""), Some("\"old\"")),
            Ok(Observation::Unknown {
                etag: Some("\"old\"".into())
            })
        );
    }

    #[test]
    fn rejects_unexpected_responses_and_unsafe_validators() {
        assert_eq!(
            classify(StatusCode::NOT_MODIFIED, None, None),
            Err(ProbeError::UnexpectedResponse)
        );
        assert_eq!(
            classify(StatusCode::FOUND, Some("\"old\""), None),
            Err(ProbeError::UnexpectedResponse)
        );
        for value in ["*", "invalid", "\"a\"\r\nX: y", "\"a\", \"b\""] {
            assert_eq!(valid_etag(value), Err(ProbeError::InvalidValidator));
        }
        assert_eq!(
            classify(StatusCode::OK, Some("\"old\""), Some("bad")),
            Ok(Observation::Unknown { etag: None })
        );
    }
}
