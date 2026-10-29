"""官方 YooAsset .hash/.bytes 傳輸完整性檢查（非資源解析或相容性驗證）。

.hash 為 YooAsset CRC32 little-endian 的 8 碼 hex。正確 CRC 只能驗證兩份
公開檔案彼此一致，不能單獨視為密碼學簽章或遊戲協定相容證據。
整份 Manifest 解析器、資產表版本適配及正式服 E2E 尚未完成。
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re
import zlib

from .official_versions import (
    ObservedVersions, OfficialVersionError, PACKAGES,
    fetch_public_bytes, package_url, parse_package_revision,
)

MAX_MANIFEST_BYTES = 8 * 1024 * 1024
_CRC = re.compile(r"[a-fA-F0-9]{8}\Z")


@dataclass(frozen=True, slots=True)
class ManifestReceipt:
    package: str
    data_version: str
    package_revision: str
    size: int
    sha256_hex: str
    crc32_le: str

    @property
    def parsed_and_compatible(self) -> bool:
        # 本階段只校驗 bytes 傳輸，不解析 YooAsset 全量資產。
        return False


@dataclass(frozen=True, slots=True)
class ManifestPair:
    exe_version: str
    data_version: str
    manifests: tuple[ManifestReceipt, ManifestReceipt]

    @property
    def catalog_key(self) -> str:
        """同版號不同內容會有不同鍵值；只能用於識別，不能解鎖功能。"""
        record = {
            "schema": 1, "exe": self.exe_version, "data": self.data_version,
            "manifests": [
                {"package": item.package, "revision": item.package_revision,
                 "sha256": item.sha256_hex, "size": item.size,
                 "crc32_le": item.crc32_le}
                for item in self.manifests
            ],
        }
        raw = json.dumps(record, ensure_ascii=True, sort_keys=True,
                         separators=(",", ":")).encode("ascii")
        return sha256(raw).hexdigest()

    @property
    def can_login(self) -> bool:
        # 尚無經審核的完整 parser、schema adapter 與伺服器協定認證。
        return False


def verify_manifest_transport(observation: ObservedVersions, package: str,
                              hash_bytes: bytes, manifest_bytes: bytes) -> ManifestReceipt:
    if not isinstance(observation, ObservedVersions) or package not in PACKAGES:
        raise OfficialVersionError("未知來源版本或 Package")
    revision = parse_package_revision(observation.package_version(package).encode("ascii"))
    if not isinstance(hash_bytes, bytes) or len(hash_bytes) != 8:
        raise OfficialVersionError("YooAsset .hash 長度必須剛好 8 bytes")
    try:
        crc_text = hash_bytes.decode("ascii").lower()
    except UnicodeError as exc:
        raise OfficialVersionError("Manifest CRC 編碼無效") from exc
    if not _CRC.fullmatch(crc_text):
        raise OfficialVersionError("Manifest .hash 格式不符")
    if not isinstance(manifest_bytes, bytes) or not 0 < len(manifest_bytes) <= MAX_MANIFEST_BYTES:
        raise OfficialVersionError("Manifest .bytes 為空或超過安全上限")
    calculated = (zlib.crc32(manifest_bytes) & 0xffffffff).to_bytes(4, "little").hex()
    if calculated != crc_text:
        raise OfficialVersionError("YooAsset .hash/.bytes CRC32LE 不一致")
    return ManifestReceipt(
        package, observation.data_version, revision,
        len(manifest_bytes), sha256(manifest_bytes).hexdigest(), calculated,
    )


def combine_manifest_receipts(observation: ObservedVersions,
                              receipts: tuple[ManifestReceipt, ...]) -> ManifestPair:
    if not isinstance(observation, ObservedVersions) or len(receipts) != 2:
        raise OfficialVersionError("必須有兩份官方 Manifest 完整性收據")
    indexed = {receipt.package: receipt for receipt in receipts
               if isinstance(receipt, ManifestReceipt)}
    if len(indexed) != 2 or set(indexed) != set(PACKAGES):
        raise OfficialVersionError("缺少或重複 Package 完整性收據")
    for name in PACKAGES:
        current = indexed[name]
        if (current.data_version != observation.data_version or
                current.package_revision != observation.package_version(name) or
                not _CRC.fullmatch(current.crc32_le) or
                not re.fullmatch("[a-f0-9]{64}", current.sha256_hex) or
                type(current.size) is not int or
                not 0 < current.size <= MAX_MANIFEST_BYTES):
            raise OfficialVersionError("Manifest 收據與版本觀察不一致")
    return ManifestPair(observation.exe_version, observation.data_version,
                        tuple(indexed[name] for name in PACKAGES))


def fetch_manifest_receipts(observation: ObservedVersions, *, fetcher=None) -> ManifestPair:
    """以該次版本觀察取得四份公開檔案，不下載任何 Bundle、不變更遊戲安裝。"""
    if not isinstance(observation, ObservedVersions):
        raise OfficialVersionError("請先取得官方版本觀察")
    fetcher = fetch_public_bytes if fetcher is None else fetcher
    receipts = []
    for name in PACKAGES:
        hash_url = package_url(observation.data_version, name, "hash")
        bytes_url = package_url(observation.data_version, name, "bytes")
        try:
            expected_crc = fetcher(hash_url, limit=8)
            manifest = fetcher(bytes_url, limit=MAX_MANIFEST_BYTES)
        except OfficialVersionError:
            raise
        except (OSError, ValueError, TypeError) as exc:
            raise OfficialVersionError("官方 Manifest 下載未完成") from exc
        receipts.append(verify_manifest_transport(
            observation, name, expected_crc, manifest))
    return combine_manifest_receipts(observation, tuple(receipts))
