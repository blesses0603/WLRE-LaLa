"""官方 PC 公開版本查詢（唯讀、HTTPS 白名單、無帳號或遊戲指令）。

由舊版 WLRe_lala/wlre/services/official_version.py 的實際觀測路徑重新設計。
版本「已觀察」不代表新版 LaLa 的封包協定或資源解析已通過驗收。
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
import socket
import gzip
import zlib
import time
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = "https://wlreftp.chinesegamer.net/WLN/TW"
VERSION_MAP_URL = ROOT + "/ResourcePath_PC.dat"
PACKAGES = ("DataPackage", "MainPackage")
MAX_VERSION_BYTES = 16384
_GAME_VERSION = re.compile(r"[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}\Z")
_PACKAGE_REVISION = re.compile(r"[1-9][0-9]{0,5}_20[0-9]{2}(?:_[0-9]{2}){6}\Z")
_APPROVED_PATH = re.compile(
    r"/WLN/TW/(?:ResourcePath_PC\.dat|"
    r"[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}/ResourcesPC/AssetBundle/"
    r"(?:DataPackage|MainPackage)\.(?:version|hash|bytes))\Z"
)


class OfficialVersionError(ValueError):
    """官方公開版本來源無法確認；不得從未驗證資料猜測相容版本。"""


@dataclass(frozen=True, slots=True)
class ObservedVersions:
    exe_version: str
    data_version: str
    package_versions: tuple[tuple[str, str], ...]
    checked_at_utc: str

    def package_version(self, name: str) -> str:
        for package, revision in self.package_versions:
            if package == name:
                return revision
        raise OfficialVersionError("未知的官方資源包")

    @property
    def protocol_compatible(self) -> bool:
        # 唯讀版本觀察無法驗證完整協定；絕不可自動放行登入。
        return False


def require_public_url(url: str) -> str:
    """禁止 SSRF、任意主機、使用者資訊、路徑穿越與非 HTTPS 轉址。"""
    if not isinstance(url, str) or any(c.isspace() for c in url):
        raise OfficialVersionError("資源來源網址格式錯誤")
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme == "https" and parsed.hostname == "wlreftp.chinesegamer.net"
            and parsed.port is None and parsed.username is None and parsed.password is None
            and (not parsed.query or (
                parsed.path == "/WLN/TW/ResourcePath_PC.dat" and
                re.fullmatch(r"[0-9]{1,20}(?:\.[0-9]{1,16})?", parsed.query) is not None
            )) and not parsed.fragment and
            _APPROVED_PATH.fullmatch(parsed.path) is not None and
            "%" not in parsed.path and "\\" not in parsed.path
        )
    except ValueError as exc:
        raise OfficialVersionError("官方來源網址無效") from exc
    if not valid:
        raise OfficialVersionError("非白名單官方 HTTPS 路徑")
    return url


def package_url(data_version: str, package: str, extension: str) -> str:
    if (not isinstance(data_version, str) or not _GAME_VERSION.fullmatch(data_version)
            or package not in PACKAGES or extension not in ("version", "hash", "bytes")):
        raise OfficialVersionError("Package 或 DataVer 不合法")
    return require_public_url(
        f"{ROOT}/{data_version}/ResourcesPC/AssetBundle/{package}.{extension}"
    )


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise OfficialVersionError("官方資源位置轉址，已拒絕")


def fetch_public_bytes(url: str, *, limit: int = MAX_VERSION_BYTES,
                       timeout: float = 10, opener=None) -> bytes:
    """只做一個唯讀 GET，嚴格限定官方路徑、回應大小、回應地址與 HTTP 200。"""
    require_public_url(url)
    if type(limit) is not int or limit < 1 or limit > 8 * 1024 * 1024:
        raise OfficialVersionError("讀取限制無效")
    if not isinstance(timeout, (int, float)) or not (0 < timeout <= 60):
        raise OfficialVersionError("連線逾時設定無效")
    if opener is None:
        opener = build_opener(_RejectRedirect()).open
    try:
        with opener(Request(url, headers={
            "Accept": "application/octet-stream, application/json, text/plain",
            "User-Agent": "WLRe-LaLa-PublicVersionCheck/1",
        }), timeout=timeout) as response:
            if (response.geturl() != url or
                    getattr(response, "status", 200) != 200):
                raise OfficialVersionError("官方來源或狀態碼與請求不符")
            declared = response.headers.get("Content-Length")
            if declared is not None:
                if not declared.isascii() or not declared.isdecimal() or int(declared) > limit:
                    raise OfficialVersionError("官方資料宣告超過安全上限")
            data = response.read(limit + 1)
            if not data or len(data) > limit:
                raise OfficialVersionError("官方資料空白或超過安全上限")
            if declared is not None and len(data) != int(declared):
                raise OfficialVersionError("官方回應內容遭截斷")
            return data
    except OfficialVersionError:
        raise
    except (OSError, HTTPError, URLError, ssl.SSLError, socket.timeout) as exc:
        # 不將例外的完整 URL、連線資訊或 TLS 堆疊印到一般使用者 UI。
        raise OfficialVersionError("官方 HTTPS 資源讀取失敗") from exc


def _decode_version_map(body: bytes) -> str:
    """相容舊版實際觀察到的 UTF-8/BOM、UTF-16 BOM 與 gzip，解壓有容量上限。"""
    if not isinstance(body, bytes) or not 0 < len(body) <= MAX_VERSION_BYTES:
        raise OfficialVersionError("官方版本對照表長度無效")
    if body.startswith(b"\x1f\x8b"):
        try:
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
            decoded = decoder.decompress(body, MAX_VERSION_BYTES + 1)
            if (len(decoded) > MAX_VERSION_BYTES or not decoder.eof or
                    decoder.unconsumed_tail or decoder.unused_data):
                raise OfficialVersionError("官方版本對照表 gzip 大小／內容不完整")
            body = decoded
        except (ValueError, zlib.error) as exc:
            raise OfficialVersionError("官方版本對照表 gzip 內容無效") from exc
    try:
        content = (body.decode("utf-16") if body.startswith((b"\xff\xfe", b"\xfe\xff"))
                   else body.decode("utf-8-sig")).strip()
    except UnicodeError as exc:
        raise OfficialVersionError("官方版本對照表編碼不是 UTF-8/UTF-16 BOM") from exc
    if content[:32].lower().startswith(("<!doctype html", "<html", "<head", "<body")):
        raise OfficialVersionError("官方 CDN 回傳 HTML，而非版本對照表")
    return content


def parse_version_map(body: bytes) -> tuple[str, str]:
    """嚴格驗證官方 ExeVer/DataVer；錯誤只報欄位與型態，不洩漏回應內容。"""
    content = _decode_version_map(body)
    # 只容忍已在舊版 Fiddler 證實的「陣列最後一個多餘逗號」。
    content = re.sub(r",(?=\s*\]\s*\Z)", "", content, count=1)
    try:
        table = json.loads(content)
    except (ValueError, UnicodeError) as exc:
        raise OfficialVersionError("官方版本對照表不是支援的 JSON 陣列") from exc
    if not isinstance(table, list) or not 1 <= len(table) <= 128:
        raise OfficialVersionError("官方版本對照表不是 1～128 筆陣列")
    versions: dict[str, str] = {}
    for index, row in enumerate(table, start=1):
        if not isinstance(row, dict):
            raise OfficialVersionError(f"官方版本表第 {index} 筆不是 JSON 物件")
        for field in ("ExeVer", "DataVer"):
            value = row.get(field)
            if not isinstance(value, str):
                kind = "缺少" if field not in row else "不是文字"
                raise OfficialVersionError(f"官方版本表第 {index} 筆 {field} {kind}；已停止自檢")
            if not _GAME_VERSION.fullmatch(value):
                # 只記錄欄位／長度，不輸出未信任的完整值或 URL。
                raise OfficialVersionError(
                    f"官方版本表第 {index} 筆 {field} 格式不符三段數字"
                    f"（長度 {len(value)}）；已停止自檢"
                )
        if row["ExeVer"] in versions:
            raise OfficialVersionError(f"官方版本表第 {index} 筆 ExeVer 重複；已停止自檢")
        versions[row["ExeVer"]] = row["DataVer"]
    newest = max(versions, key=lambda s: tuple(int(x) for x in s.split(".")))
    return newest, versions[newest]


def parse_package_revision(body: bytes) -> str:
    if not isinstance(body, bytes) or not 1 <= len(body) <= 128:
        raise OfficialVersionError("官方 Package 修訂資料長度無效")
    try:
        text = body.decode("utf-8-sig").strip()
    except UnicodeError as exc:
        raise OfficialVersionError("Package 修訂編碼無效") from exc
    if not _PACKAGE_REVISION.fullmatch(text):
        raise OfficialVersionError("Package 修訂號必須包含完整版本與時間戳")
    return text


def observe_official_versions(*, fetcher=None, checked_at_utc=None) -> ObservedVersions:
    """恰好三個官方公開 GET，不自動連線遊戲、不寫入快取、不取得角色資料。"""
    fetcher = fetch_public_bytes if fetcher is None else fetcher
    try:
        # Older official clients have used an unkeyed numeric cache-buster.
        # If the canonical response is malformed, retry this exact approved
        # public file once with a numeric nonce; never guess DataVer.
        map_body = fetcher(VERSION_MAP_URL)
        try:
            exe, data_ver = parse_version_map(map_body)
        except OfficialVersionError as initial:
            try:
                fresh_url = VERSION_MAP_URL + "?" + str(time.time_ns())
                exe, data_ver = parse_version_map(fetcher(fresh_url))
            except (OfficialVersionError, OSError, TypeError, ValueError, KeyError) as retry_error:
                # Preserve the initial field-level diagnostic without leaking
                # untrusted server content, URL, or transport exception text.
                raise OfficialVersionError(
                    str(initial) + "；同一官方來源重新查詢仍未通過驗證"
                ) from retry_error
        versions = tuple((package, parse_package_revision(fetcher(package_url(
            data_ver, package, "version")))) for package in PACKAGES)
    except OfficialVersionError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise OfficialVersionError("無法確認官方版本，未更新任何資源") from exc
    now = checked_at_utc or datetime.now(timezone.utc).isoformat(timespec="seconds")
    return ObservedVersions(exe, data_ver, versions, now)
