"""安裝 LaLa 啟動所需官方 YooAsset Manifest 索引；未完成不得進入主介面。

只處理兩份經官方公開 HTTPS 來源驗證的 Manifest 索引，不任意下載全量
Unity Bundle 或修改使用者遊戲目錄。離線 UI 啟動就緒 != 正式服登入就緒。
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
import zlib

from .manifest_transport import verify_manifest_transport, combine_manifest_receipts, MAX_MANIFEST_BYTES
from .official_versions import (
    OfficialVersionError, ObservedVersions, PACKAGES, fetch_public_bytes,
    observe_official_versions, package_url,
)
from .yooasset_index import parse_manifest


INSTALL_SCHEMA = 1
INDEX_FILES = {"DataPackage": "DataPackage.bytes", "MainPackage": "MainPackage.bytes"}


def default_resource_root() -> Path:
    """所有內容只放在本機私有資料區，不覆蓋原遊戲、GitHub 專案或系統 Python。"""
    local = os.environ.get("LOCALAPPDATA")
    if os.name == "nt" and local:
        return Path(local) / "WLRe-LaLa" / "official_sync" / "indexes"
    return Path.home() / ".local" / "share" / "WLRe-LaLa" / "official_sync" / "indexes"


def _crc32_le(data: bytes) -> str:
    return (zlib.crc32(data) & 0xffffffff).to_bytes(4, "little").hex()


def _atomic_json(path: Path, data: dict) -> None:
    """檔案先同步到磁碟再置換；中斷時舊安裝標記保持不變。"""
    pending = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=path.parent, prefix=".index-receipt-",
                                         delete=False) as writer:
            pending = Path(writer.name)
            json.dump(data, writer, ensure_ascii=False, sort_keys=True)
            writer.write("\n")
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(pending, path)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def _validate_existing(destination: Path, receipt: dict, data: dict[str, bytes]) -> bool:
    if destination.is_symlink():
        raise OfficialVersionError("本機官方索引快取路徑是符號連結，拒絕使用")
    if not destination.exists():
        return False
    if not destination.is_dir():
        raise OfficialVersionError("本機官方索引安裝位置不是目錄")
    try:
        marker = destination / "installed.json"
        if marker.is_symlink() or json.loads(marker.read_text("utf-8")) != receipt:
            raise OfficialVersionError("既有索引安裝收據與官方內容不符")
        for name in PACKAGES:
            file = destination / INDEX_FILES[name]
            entry = receipt["manifests"][name]
            if file.is_symlink() or not file.is_file() or file.stat().st_size != entry["size"]:
                raise OfficialVersionError("既有索引檔案遺失或大小不符")
            # Always re-verify local bytes, even when a receipt exists.
            local_bytes = file.read_bytes()
            if (sha256(local_bytes).hexdigest() != entry["sha256"] or
                    _crc32_le(local_bytes) != entry["crc32_le"] or
                    local_bytes != data[name]):
                raise OfficialVersionError("既有索引檔案與官方資料不相符")
        return True
    except (OSError, ValueError, UnicodeError) as exc:
        raise OfficialVersionError("既有索引安裝快取無法驗證，拒絕開啟主程式") from exc


def install_index(*, observation: ObservedVersions, fetcher=None,
                  root: Path | str | None = None, verify_latest=None) -> dict:
    """先完整下載／解析兩包，再原子安裝版本化快取；不發遊戲封包。

    verify_latest 為可選的再次觀察來源；正式啟動應使用此機制，
    以免檢查過程中官方版本更新而安裝過期索引。
    """
    if not isinstance(observation, ObservedVersions):
        raise OfficialVersionError("必須先驗證官方版本")
    fetcher = fetch_public_bytes if fetcher is None else fetcher
    data: dict[str, bytes] = {}
    receipts, indexes = [], []
    for name in PACKAGES:
        try:
            official_crc = fetcher(package_url(observation.data_version, name, "hash"),
                                   limit=8)
            blob = fetcher(package_url(observation.data_version, name, "bytes"),
                           limit=MAX_MANIFEST_BYTES)
            receipt = verify_manifest_transport(observation, name, official_crc, blob)
            index = parse_manifest(blob, package=name, revision=receipt.package_revision)
        except OfficialVersionError:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise OfficialVersionError("官方索引下載／解析未完成，禁止開啟主程式") from exc
        data[name] = blob
        receipts.append(receipt)
        indexes.append(index)

    pair = combine_manifest_receipts(observation, tuple(receipts))
    manifests = {
        index.package: {
            "revision": index.revision,
            "size": receipt.size,
            "sha256": receipt.sha256_hex,
            "crc32_le": receipt.crc32_le,
            "asset_count": len(index.assets),
            "bundle_count": len(index.bundles),
        }
        for index, receipt in zip(indexes, receipts)
    }
    marker = {
        "schema": INSTALL_SCHEMA,
        "catalog_key": pair.catalog_key,
        "exe_version": observation.exe_version,
        "data_version": observation.data_version,
        "package_versions": dict(observation.package_versions),
        "manifests": manifests,
        "index_installed": True,
        "gameplay_schema_validated": False,
        "gameplay_protocol_verified": False,
        "bundles_installed": False,
    }

    # Do not create an install marker when the CDN updates mid-run.
    if verify_latest is not None:
        newest = verify_latest()
        if (not isinstance(newest, ObservedVersions) or
                newest.exe_version != observation.exe_version or
                newest.data_version != observation.data_version or
                newest.package_versions != observation.package_versions):
            raise OfficialVersionError("官方資源版本在自檢期間變動；本次安裝取消")

    base = default_resource_root() if root is None else Path(root)
    if base.is_symlink():
        raise OfficialVersionError("索引資料根目錄不可為符號連結")
    base.mkdir(parents=True, exist_ok=True)
    destination = base / pair.catalog_key
    existing = _validate_existing(destination, marker, data)
    if not existing:
        pending = Path(tempfile.mkdtemp(prefix=".install-", dir=base))
        try:
            for name in PACKAGES:
                path = pending / INDEX_FILES[name]
                with path.open("xb") as writer:
                    writer.write(data[name])
                    writer.flush()
                    os.fsync(writer.fileno())
            _atomic_json(pending / "installed.json", marker)
            # Only publish all-or-nothing after both manifests + receipt exist.
            if destination.exists() or destination.is_symlink():
                # Another process finished concurrently: validate, never overwrite.
                _validate_existing(destination, marker, data)
                existing = True
            else:
                try:
                    os.rename(pending, destination)
                except OSError:
                    if not _validate_existing(destination, marker, data):
                        raise
                    existing = True
            if not _validate_existing(destination, marker, data):
                raise OfficialVersionError("原子安裝後校驗失敗")
        finally:
            if pending.exists():
                shutil.rmtree(pending)

    # This receipt is a pointer to a verified local index, not permission to login.
    _atomic_json(base / "current.json", {
        "schema": INSTALL_SCHEMA,
        "catalog_key": pair.catalog_key,
        "data_version": observation.data_version,
    })
    return {
        "status": "index_installed",
        "index_installed": True,
        "reused_verified_cache": existing,
        "catalog_key": pair.catalog_key,
        "exe_version": observation.exe_version,
        "data_version": observation.data_version,
        "manifests": manifests,
        "all_required_bundles_installed": False,
        "gameplay_schema_validated": False,
        "gameplay_protocol_verified": False,
        "can_open_ui": True,
        "can_login": False,
    }


def bootstrap(*, root=None, fetcher=None, timeout=3.0,
              observer=None, recheck=None) -> dict:
    if not 0 < timeout <= 60:
        raise OfficialVersionError("官方資源查詢逾時設定無效")
    if fetcher is None:
        fetcher = lambda url, *, limit=16384: fetch_public_bytes(
            url, limit=limit, timeout=timeout)
    if observer is None:
        observer = lambda: observe_official_versions(fetcher=fetcher)
    if recheck is None:
        recheck = observer
    observation = observer()
    return install_index(observation=observation, fetcher=fetcher,
                         root=root, verify_latest=recheck)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="LaLa 啟動前官方索引校驗／原子安裝")
    parser.add_argument("--online", action="store_true",
                        help="明確允許只讀官方 HTTPS 資源查詢與 Manifest 下載")
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.online:
        parser.error("啟動前安裝必須明確加入 --online")
    try:
        result = bootstrap(timeout=args.timeout)
    except (OfficialVersionError, OSError) as exc:
        # Never print remote payload, user credentials or local absolute paths.
        parser.exit(1, "LaLa 官方索引安裝失敗：" + (
            str(exc) if isinstance(exc, OfficialVersionError)
            else "本機快取存取失敗") + "\n")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("官方索引安裝完成：", result["catalog_key"])
        print("遊戲資料 Bundle 與正式服登入：尚未完成驗證")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
