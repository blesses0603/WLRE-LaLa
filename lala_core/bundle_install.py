"""Verified YooAsset Bundle downloads into LaLa's private user cache.

Specs originate ONLY from the CRC-verified, fully parsed official Manifest.
No game-install modification, no arbitrary URL, no inferred asset filename.
A file is *installed* only after size + MD5 + CRC32LE checks and os.replace.
"""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import tempfile
from urllib.request import Request, HTTPRedirectHandler, build_opener
from urllib.error import URLError, HTTPError
import zlib

from .official_versions import ROOT, OfficialVersionError, package_url
from .yooasset_index import ParsedCatalog


MAX_BUNDLE_BYTES = 256 * 1024 * 1024
READ_CHUNK = 64 * 1024
_BUNDLE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,190}\.bundle\Z")
_MD5 = re.compile(r"[a-fA-F0-9]{32}\Z")
_CRC = re.compile(r"[a-fA-F0-9]{8}\Z")


class InstallError(ValueError):
    """Verification or download failed; runtime is NOT ready."""


@dataclass(frozen=True, slots=True)
class BundleSpec:
    data_ver: str
    package: str
    revision: str
    name: str
    size: int
    md5_hex: str
    crc32_le: str

    def __post_init__(self):
        from .official_versions import PACKAGES, parse_package_revision
        try:
            package_url(self.data_ver, self.package, "bytes")
            parse_package_revision(self.revision.encode("ascii"))
        except (OfficialVersionError, UnicodeError, AttributeError) as error:
            raise InstallError("Bundle 來源版本無效") from error
        if (self.package not in PACKAGES or
                not isinstance(self.name, str) or
                _BUNDLE_NAME.fullmatch(self.name) is None or
                type(self.size) is not int or not 0 < self.size <= MAX_BUNDLE_BYTES or
                not isinstance(self.md5_hex, str) or not _MD5.fullmatch(self.md5_hex) or
                not isinstance(self.crc32_le, str) or not _CRC.fullmatch(self.crc32_le)):
            raise InstallError("官方 Manifest Bundle 身分／大小／雜湊不合法")

    @property
    def url(self):
        # No redirects, query strings, path traversals or arbitrary hosts.
        return ROOT + "/" + self.data_ver + "/ResourcesPC/AssetBundle/" + self.name

    def path(self, root):
        root = Path(root)
        return root / "bundles" / self.package / self.revision / self.md5_hex.lower() / self.name


def build_bundle_specs(catalog: ParsedCatalog) -> tuple[BundleSpec, ...]:
    """Use ALL Bundle records from both official manifests, not guessed subsets."""
    if (not isinstance(catalog, ParsedCatalog) or
            len(catalog.indexes) != 2 or len(catalog.transport.manifests) != 2):
        raise InstallError("缺少兩包已驗證的官方索引")
    specs = []
    for index, receipt in zip(catalog.indexes, catalog.transport.manifests):
        if index.package != receipt.package or index.revision != receipt.package_revision:
            raise InstallError("Manifest 與官方修訂版號不符")
        for bundle in index.bundles:
            specs.append(BundleSpec(
                catalog.transport.data_version, index.package, index.revision,
                bundle.name, bundle.file_size, bundle.file_hash, bundle.file_crc))
    if not specs:
        raise InstallError("官方 Manifest 沒有可安裝 Bundle")
    return tuple(specs)


def _digest_file(path: Path, spec: BundleSpec) -> bool:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size != spec.size:
            return False
        md5 = hashlib.md5(usedforsecurity=False)
        crc = 0
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(READ_CHUNK), b""):
                md5.update(chunk)
                crc = zlib.crc32(chunk, crc)
        return (md5.hexdigest() == spec.md5_hex.lower() and
                (crc & 0xffffffff).to_bytes(4, "little").hex() ==
                spec.crc32_le.lower())
    except OSError:
        return False


def is_verified(spec: BundleSpec, root) -> bool:
    return _digest_file(spec.path(root), spec)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise InstallError("官方 Bundle 重新導向，拒絕下載")


def download_verified(spec: BundleSpec, root, *, opener=None, timeout=20):
    """Stream one approved official URL; reuse only digest-verified local files."""
    if not isinstance(spec, BundleSpec):
        raise InstallError("Bundle 規格來源無效")
    if not isinstance(timeout, (int, float)) or not 0 < timeout <= 60:
        raise InstallError("下載逾時設定無效")
    dest = spec.path(root)
    if is_verified(spec, root):
        return dest, False
    # Each component of the destination path is derived from strictly validated
    # manifest fields, never user-supplied absolute paths.
    dest.parent.mkdir(parents=True, exist_ok=True)
    if any(part.is_symlink() for part in (dest.parent, *dest.parents)):
        raise InstallError("快取路徑含符號連結，拒絕寫入")
    opener = build_opener(_NoRedirect()).open if opener is None else opener
    tmp = None
    try:
        with opener(Request(spec.url, headers={"User-Agent": "WLRe-LaLa-OfficialAssets/1"}),
                    timeout=timeout) as response:
            if response.geturl() != spec.url or getattr(response, "status", 200) != 200:
                raise InstallError("官方 Bundle 回應網址／狀態不符")
            declared = response.headers.get("Content-Length")
            if declared is not None and (
                    not declared.isascii() or not declared.isdecimal() or
                    int(declared) != spec.size):
                raise InstallError("Bundle 大小與官方 Manifest 不符")
            md5 = hashlib.md5(usedforsecurity=False)
            crc, count = 0, 0
            with tempfile.NamedTemporaryFile(
                    dir=dest.parent, prefix=".lala_bundle_", suffix=".partial",
                    delete=False) as stream:
                tmp = Path(stream.name)
                while True:
                    chunk = response.read(READ_CHUNK)
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > spec.size:
                        raise InstallError("Bundle 內容超出官方大小")
                    md5.update(chunk)
                    crc = zlib.crc32(chunk, crc)
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
        if (count != spec.size or md5.hexdigest() != spec.md5_hex.lower() or
                (crc & 0xffffffff).to_bytes(4, "little").hex() !=
                spec.crc32_le.lower()):
            raise InstallError("Bundle MD5／CRC32LE／長度驗證失敗")
        os.replace(tmp, dest)
        return dest, True
    except InstallError:
        raise
    except (OSError, URLError, HTTPError) as error:
        raise InstallError("官方 Bundle 下載中斷或檔案無法寫入") from error
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
