"""Mandatory official resource install gate before launching LaLa.

Fresh CDN versions + both CRC-verified YooAsset indexes -> all Bundle records
-> cache reuse or verified downloads -> atomic receipt. No game server packets.
"""
import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from .bundle_install import InstallError, build_bundle_specs, download_verified, is_verified
from .manifest_transport import MAX_MANIFEST_BYTES, verify_manifest_transport, combine_manifest_receipts
from .official_versions import (OfficialVersionError, ObservedVersions, PACKAGES,
                                observe_official_versions, fetch_public_bytes, package_url)
from .yooasset_index import ParsedCatalog, fetch_parsed_catalog, parse_manifest

MAX_DOWNLOAD_BYTES = 32 * 1024**3
MAX_FILES = 100000


def private_root():
    # Keep copyrighted raw resources out of the Git tree / game installation.
    base = os.environ.get("LOCALAPPDATA") if os.name == "nt" else None
    return (Path(base) if base else Path.home() / ".local" / "share") / "LaLa" / "official_resources"


def _atomic(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise InstallError("資源快取路徑包含符號連結")
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".lala_",
                                         suffix=".partial", delete=False) as out:
            temp = Path(out.name)
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def _manifest_path(root, package, revision):
    from .official_versions import parse_package_revision
    if package not in PACKAGES or not isinstance(revision, str):
        raise InstallError("未知官方 Package")
    parse_package_revision(revision.encode("ascii"))
    return Path(root) / "manifests" / package / revision / (package + ".bytes")


@dataclass(frozen=True)
class InstallResult:
    catalog_key: str
    data_version: str
    files_total: int
    files_downloaded: int
    files_reused: int
    total_size_bytes: int
    resources_installed: bool = True
    can_login: bool = False


def _marker(catalog, specs):
    return {
        "schema": 1, "catalog_key": catalog.transport.catalog_key,
        "exe_version": catalog.transport.exe_version,
        "data_version": catalog.transport.data_version,
        "packages": {
            r.package: {
                "revision": r.package_revision, "sha256": r.sha256_hex,
                "crc32_le": r.crc32_le, "size": r.size,
            } for r in catalog.transport.manifests
        },
        "bundle_count": len(specs), "bundle_bytes": sum(s.size for s in specs),
        "resources_installed": True, "can_login": False, "protocol_compatible": False,
    }


def install_resources(*, root=None, observer=None, fetcher=None, opener=None,
                      timeout=20, max_total_bytes=MAX_DOWNLOAD_BYTES,
                      max_files=MAX_FILES, progress=None, check_disk=True):
    """Install all manifest-listed files, not just an unreviewed 'minimum' subset.

    An interrupted install leaves verified downloaded files reusable next time,
    but cannot create the success marker.
    """
    root = private_root() if root is None else Path(root)
    # Never place downloaded game content in the source repository.
    target = root.expanduser().resolve()
    if any((ancestor / ".git").exists() for ancestor in (target, *target.parents)):
        raise InstallError("禁止將官方遊戲資源安裝至 Git 工作樹")
    if type(max_total_bytes) is not int or not 0 < max_total_bytes <= 256*1024**3:
        raise InstallError("安裝大小配額不合法")
    if type(max_files) is not int or not 0 < max_files <= 200000:
        raise InstallError("安裝檔案數量配額不合法")
    if not isinstance(timeout, (float, int)) or not 0 < timeout <= 60:
        raise InstallError("官方網路逾時設定不合法")
    if observer is None:
        observer = lambda: observe_official_versions(
            fetcher=lambda url: fetch_public_bytes(url, timeout=timeout))
    if fetcher is None:
        fetcher = lambda url, *, limit: fetch_public_bytes(url, limit=limit, timeout=timeout)
    first_versions = observer()
    catalog = fetch_parsed_catalog(first_versions, fetcher=fetcher)
    if len(catalog.manifest_bytes) != 2:
        raise InstallError("官方 Manifest 並未完整取得")
    specs = build_bundle_specs(catalog)
    if len(specs) > max_files or sum(s.size for s in specs) > max_total_bytes:
        raise InstallError("官方資源超出本次下載安全配額；未開啟主程式")
    missing = [spec for spec in specs if not is_verified(spec, root)]
    required = sum(s.size for s in missing)
    if check_disk and required:
        root.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(root).free < required + 512 * 1024**2:
            raise InstallError("硬碟可用空間不足，未開始安裝")
    # A previously valid catalog must not authorize direct GUI entry if a
    # newer official catalog is currently being installed or that update
    # stops midway. Only completing all verification clears this sentinel.
    # Keep it on interruption to fail closed; a later successful install
    # safely overwrites the staged marker and removes it.
    _atomic(root / "install.pending", json.dumps({
        "schema": 1, "catalog_key": catalog.transport.catalog_key,
    }, sort_keys=True).encode("ascii"))
    downloaded = 0
    missing_ids = {(s.package, s.revision, s.name) for s in missing}
    for i, spec in enumerate(specs, start=1):
        if (spec.package, spec.revision, spec.name) in missing_ids:
            download_verified(spec, root, opener=opener, timeout=timeout)
            downloaded += 1
        if progress is not None:
            progress(i, len(specs), downloaded)
    # Guard against official updates during a long installation. A freshly
    # observed version AND both current CRC texts must match the originals.
    # Otherwise do NOT publish a "ready" marker for mixed-version resources.
    latest = observer()
    if (latest.exe_version != first_versions.exe_version or
            latest.data_version != first_versions.data_version or
            latest.package_versions != first_versions.package_versions):
        raise InstallError("下載期間官方版本已更新；請重新啟動安裝")
    for receipt in catalog.transport.manifests:
        remote_hash = fetcher(
            package_url(first_versions.data_version, receipt.package, "hash"), limit=8)
        if (not isinstance(remote_hash, bytes) or
                remote_hash.decode("ascii", "ignore").lower() != receipt.crc32_le):
            raise InstallError("下載期間官方 Manifest 已變更；請重新啟動安裝")
    # Detect races or corruption before publishing a completed install.
    if any(not is_verified(spec, root) for spec in specs):
        raise InstallError("安裝後複查 Bundle 失敗")
    for blob, receipt in zip(catalog.manifest_bytes, catalog.transport.manifests):
        if (hashlib.sha256(blob).hexdigest() != receipt.sha256_hex or
                len(blob) != receipt.size):
            raise InstallError("Manifest 下載期間內容改變")
        _atomic(_manifest_path(root, receipt.package, receipt.package_revision), blob)
    marker = json.dumps(_marker(catalog, specs), sort_keys=True, ensure_ascii=True).encode()
    if len(marker) > 4096:
        raise InstallError("資源安裝清單過大")
    _atomic(root / "installed.json", marker)
    # Never remove the pending marker before the completed receipt exists.
    (root / "install.pending").unlink()
    return InstallResult(catalog.transport.catalog_key, catalog.transport.data_version,
                         len(specs), downloaded, len(specs)-downloaded, sum(s.size for s in specs))


def verify_installed(*, root=None, expected_catalog_key=None):
    """Offline verification gate for direct pythonw / python -m lala_desktop."""
    root = private_root() if root is None else Path(root)
    receipt = root / "installed.json"
    try:
        # A partial/in-flight update is not a completed installation even
        # when an older installed.json still exists on disk.
        if (root / "install.pending").exists() or (root / "install.pending").is_symlink():
            raise InstallError("官方資源正在安裝或更新失敗，須完成驗證後才能進入")
        if receipt.is_symlink() or receipt.stat().st_size > 4096:
            raise InstallError("安裝憑證無效")
        marker = json.loads(receipt.read_text(encoding="ascii"))
        if (type(marker) is not dict or marker.get("schema") != 1 or
                marker.get("resources_installed") is not True or
                marker.get("can_login") is not False or
                marker.get("protocol_compatible") is not False or
                not isinstance(marker.get("catalog_key"), str) or
                len(marker["catalog_key"]) != 64 or
                type(marker.get("packages")) is not dict or
                set(marker["packages"]) != set(PACKAGES)):
            raise InstallError("安裝憑證內容無效")
        if expected_catalog_key is not None and marker["catalog_key"] != expected_catalog_key:
            raise InstallError("本次官方版本與快取版本不符")
        versions = ObservedVersions(
            marker["exe_version"], marker["data_version"],
            tuple((p, marker["packages"][p]["revision"]) for p in PACKAGES), "cached")
        receipts, indexes = [], []
        for package in PACKAGES:
            package_url(versions.data_version, package, "bytes")
            info = marker["packages"][package]
            if type(info) is not dict or set(info) != {"revision", "sha256", "crc32_le", "size"}:
                raise InstallError("Manifest 安裝憑證無效")
            manifest = _manifest_path(root, package, versions.package_version(package))
            if manifest.is_symlink() or not 0 < manifest.stat().st_size <= MAX_MANIFEST_BYTES:
                raise InstallError("Manifest 快取缺失或超限")
            blob = manifest.read_bytes()
            if type(info["crc32_le"]) is not str:
                raise InstallError("Manifest CRC 不合法")
            result = verify_manifest_transport(
                versions, package, info["crc32_le"].encode("ascii"), blob)
            if result.sha256_hex != info["sha256"] or result.size != info["size"]:
                raise InstallError("Manifest 快取與紀錄不一致")
            receipts.append(result)
            indexes.append(parse_manifest(
                blob, package=package, revision=result.package_revision))
        pair = combine_manifest_receipts(versions, tuple(receipts))
        catalog = ParsedCatalog(pair, tuple(indexes))
        specs = build_bundle_specs(catalog)
        if (pair.catalog_key != marker["catalog_key"] or
                type(marker.get("bundle_count")) is not int or
                marker["bundle_count"] != len(specs) or
                type(marker.get("bundle_bytes")) is not int or
                marker["bundle_bytes"] != sum(s.size for s in specs)):
            raise InstallError("安裝清單版本或數量不一致")
        if any(not is_verified(spec, root) for spec in specs):
            raise InstallError("Bundle 快取遺失或校驗失敗")
        return marker
    except (OSError, TypeError, KeyError, ValueError, UnicodeError, AttributeError) as exc:
        raise InstallError("官方資源尚未完整安裝或檔案損毀，請重新啟動 BAT") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description="LaLa 入門前官方資源索引、下載安裝強制檢查")
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--max-gib", type=int, default=32)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.online or not args.install:
        parser.error("需同時指定 --online --install")
    if not 1 <= args.max_gib <= 256:
        parser.error("--max-gib 需介於 1～256")
    last = [-1]
    def show_progress(done, total, downloaded):
        percent = done * 100 // total
        if percent // 5 != last[0] // 5 or done == total:
            last[0] = percent
            print(f"[LaLa] 官方資源：{percent}%（{done}/{total}；新下載 {downloaded}）",
                  file=sys.stderr, flush=True)
    try:
        result = install_resources(
            timeout=args.timeout, max_total_bytes=args.max_gib * 1024**3,
            progress=show_progress)
        verify_installed(expected_catalog_key=result.catalog_key)
    except (InstallError, OfficialVersionError, OSError) as error:
        print("[LaLa] 官方資源安裝失敗：" + str(error), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    else:
        print("[LaLa] 兩包 Manifest 已解析；所有 Bundle 安裝與複查完成。")
        print(f"[LaLa] 共 {result.files_total} 檔，本次下載 {result.files_downloaded}。")
        print("[LaLa] 遊戲登入協定尚未驗證；僅開放 LaLa 介面。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
