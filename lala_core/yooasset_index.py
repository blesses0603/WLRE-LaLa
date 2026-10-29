"""YooAsset 2.2.5 full, bounded read-only manifest index parser.

Rewritten from reviewed legacy LaLa format observations (YooAsset 2.2.10
uses file_version 2.2.5). Does not extract copyrighted Bundle contents,
write game data or authorize any game commands.
"""
from dataclasses import dataclass
import struct

from .manifest_transport import (
    ManifestPair, MAX_MANIFEST_BYTES, verify_manifest_transport,
    combine_manifest_receipts,
)
from .official_versions import (
    ObservedVersions, OfficialVersionError, PACKAGES,
    fetch_public_bytes, package_url,
)


MAGIC = 0x00594F4F
FORMAT = "2.2.5"
MAX_RECORDS = 200_000


@dataclass(frozen=True, slots=True)
class IndexedAsset:
    path: str
    bundle_id: int


@dataclass(frozen=True, slots=True)
class IndexedBundle:
    name: str
    file_size: int
    dependencies: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ParsedManifest:
    package: str
    revision: str
    file_version: str
    output_name_style: int
    assets: tuple[IndexedAsset, ...]
    bundles: tuple[IndexedBundle, ...]

    def summary(self) -> dict:
        return {
            "package": self.package,
            "revision": self.revision,
            "yooasset_format": self.file_version,
            "asset_count": len(self.assets),
            "bundle_count": len(self.bundles),
            "dependencies_checked": True,
            "asset_schema_validated": False,
            "gameplay_compatible": False,
        }

    def find_bundle_for_path(self, exact_path: str) -> IndexedBundle | None:
        """Only an exact reviewed asset path can be resolved; no guesses."""
        for asset in self.assets:
            if asset.path == exact_path:
                return self.bundles[asset.bundle_id]
        return None


@dataclass(frozen=True, slots=True)
class ParsedCatalog:
    transport: ManifestPair
    indexes: tuple[ParsedManifest, ParsedManifest]
    # Parsed binary structure alone is NOT sufficient to authenticate to game.
    protocol_compatible: bool = False

    @property
    def can_login(self) -> bool:
        return False


class _Reader:
    def __init__(self, data):
        if not isinstance(data, bytes) or not 0 < len(data) <= MAX_MANIFEST_BYTES:
            raise OfficialVersionError("YooAsset Manifest 大小無效")
        self.data = memoryview(data)
        self.at = 0

    def take(self, length):
        if type(length) is not int or length < 0 or self.at + length > len(self.data):
            raise OfficialVersionError("Manifest 二進位欄位截斷")
        result = self.data[self.at:self.at + length]
        self.at += length
        return result

    def number(self, format):
        return struct.unpack("<" + format, self.take(struct.calcsize("<" + format)))[0]

    def u8(self): return self.number("B")
    def u16(self): return self.number("H")
    def u32(self): return self.number("I")
    def i32(self): return self.number("i")
    def i64(self): return self.number("q")

    def boolean(self):
        x = self.u8()
        if x not in (0, 1):
            raise OfficialVersionError("YooAsset 布林欄位無效")
        return bool(x)

    def text(self, *, max_length=2048):
        length = self.u16()
        if length > max_length:
            raise OfficialVersionError("Manifest 字串欄位超出上限")
        try:
            text = self.take(length).tobytes().decode("utf-8", "strict")
        except UnicodeError as exc:
            raise OfficialVersionError("Manifest 字串編碼錯誤") from exc
        if "\x00" in text:
            raise OfficialVersionError("Manifest 字串含有空字元")
        return text

    def strings(self):
        count = self.u16()
        if count > 1024:
            raise OfficialVersionError("Manifest 標籤數過多")
        return tuple(self.text(max_length=512) for _ in range(count))

    def ids(self):
        count = self.u16()
        if count > 1024:
            raise OfficialVersionError("Manifest 相依數過多")
        return tuple(self.i32() for _ in range(count))

    def count(self):
        count = self.i32()
        if not 0 <= count <= MAX_RECORDS:
            raise OfficialVersionError("Manifest 記錄數量超出上限")
        return count


def parse_manifest(data: bytes, *, package: str, revision: str) -> ParsedManifest:
    """Validate full 2.2.5 asset/bundle structure and cross references.

    Fails closed on unsupported format or package revision and never echoes
    untrusted asset paths in errors/logs.
    """
    if package not in PACKAGES or not isinstance(revision, str):
        raise OfficialVersionError("未知 Package 或修訂身分")
    r = _Reader(data)
    if r.u32() != MAGIC:
        raise OfficialVersionError("YooAsset Manifest 魔術標記不符")
    format_name = r.text(max_length=32)
    if format_name != FORMAT:
        raise OfficialVersionError("YooAsset Manifest 格式未驗證")
    r.boolean()  # addressable
    r.boolean()  # lower location
    r.boolean()  # include GUID
    output_style = r.i32()
    r.i32()  # bundle build type
    r.text(max_length=256)  # pipeline
    actual_package = r.text(max_length=64)
    actual_revision = r.text(max_length=128)
    r.text(max_length=1024)  # package note, not displayed
    if actual_package != package or actual_revision != revision:
        raise OfficialVersionError("Manifest 內嵌 Package 版本與官方觀察不同")
    if output_style != 1:
        raise OfficialVersionError("尚未核對此 YooAsset Bundle 命名策略")

    count = r.count()
    assets = []
    seen_paths = set()
    for _ in range(count):
        r.text(max_length=2048)  # address; not persisted
        path = r.text(max_length=2048)
        r.text(max_length=256)  # GUID
        r.strings()  # asset tags
        bid = r.i32()
        if not path or path in seen_paths:
            raise OfficialVersionError("Manifest AssetPath 空白或重複")
        seen_paths.add(path)
        assets.append(IndexedAsset(path, bid))

    count = r.count()
    bundles = []
    seen_names = set()
    for _ in range(count):
        name = r.text(max_length=2048)
        r.u32()  # Unity CRC
        r.text(max_length=256)  # file hash
        r.text(max_length=256)  # file CRC
        size = r.i64()
        r.boolean()  # encrypted
        r.strings()
        depends = r.ids()
        if not name or name in seen_names or size < 0:
            raise OfficialVersionError("Manifest Bundle 名稱／大小異常")
        seen_names.add(name)
        bundles.append(IndexedBundle(name, size, depends))

    if r.at != len(r.data):
        raise OfficialVersionError("Manifest 尾端出現未知資料")
    for asset in assets:
        if not 0 <= asset.bundle_id < len(bundles):
            raise OfficialVersionError("Manifest Asset 指向不存在的 Bundle")
    for index, bundle in enumerate(bundles):
        if index in bundle.dependencies or len(set(bundle.dependencies)) != len(bundle.dependencies):
            raise OfficialVersionError("Manifest 相依 Bundle 重複或自我參照")
        if any(dep < 0 or dep >= len(bundles) for dep in bundle.dependencies):
            raise OfficialVersionError("Manifest Bundle 相依索引越界")
    return ParsedManifest(package, revision, format_name, output_style,
                          tuple(assets), tuple(bundles))


def fetch_parsed_catalog(observation: ObservedVersions, *, fetcher=None) -> ParsedCatalog:
    """Four HTTPS GETs after official version observation, in memory only.

    Verify each manifest CRC first; only parse bytes if transport is correct.
    """
    if not isinstance(observation, ObservedVersions):
        raise OfficialVersionError("缺少官方版本觀察")
    fetcher = fetch_public_bytes if fetcher is None else fetcher
    receipts, indexes = [], []
    for package in PACKAGES:
        try:
            crc = fetcher(package_url(observation.data_version, package, "hash"), limit=8)
            data = fetcher(package_url(observation.data_version, package, "bytes"),
                           limit=MAX_MANIFEST_BYTES)
        except OfficialVersionError:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise OfficialVersionError("下載官方 Manifest 失敗") from exc
        receipt = verify_manifest_transport(observation, package, crc, data)
        index = parse_manifest(data, package=package, revision=receipt.package_revision)
        receipts.append(receipt)
        indexes.append(index)
    pair = combine_manifest_receipts(observation, tuple(receipts))
    return ParsedCatalog(pair, tuple(indexes))
