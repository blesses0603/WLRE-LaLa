"""只在明確 --online 時讀取官方公開版號與 Manifest；不連遊戲帳號。

執行：python -m lala_core.resource_inspector --online [--manifests] [--json]
任何成功檢查都不等於可以登入，因為尚缺 YooAsset 完整 parser/Schema/協定 E2E。
"""
import argparse
import json
from .manifest_transport import fetch_manifest_receipts
from .official_versions import (OfficialVersionError, observe_official_versions,
                                fetch_public_bytes)


def inspect(*, with_manifests=False, observer=None, manifest_fetcher=None):
    observer = observe_official_versions if observer is None else observer
    observation = observer()
    result = {
        "status": "observed_only",
        "exe_version": observation.exe_version,
        "data_version": observation.data_version,
        "package_versions": dict(observation.package_versions),
        "checked_at_utc": observation.checked_at_utc,
        "manifest_transport_checked": False,
        "catalog_parsed": False,
        "protocol_compatible": False,
        "can_login": False,
    }
    if with_manifests:
        pair = fetch_manifest_receipts(observation, fetcher=manifest_fetcher)
        result.update(
            status="manifest_transport_checked_only",
            manifest_transport_checked=True,
            catalog_identity=pair.catalog_key,
            manifests={
                item.package: {
                    "size": item.size, "sha256": item.sha256_hex,
                    "crc32_le": item.crc32_le,
                } for item in pair.manifests
            },
        )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="LaLa 唯讀官方版本檢查，永遠不登入遊戲，不解鎖操作功能")
    parser.add_argument("--online", action="store_true",
                        help="明確允許向已核對的官方 HTTPS 主機發出唯讀 GET")
    parser.add_argument("--manifests", action="store_true",
                        help="額外讀取兩份 Manifest.hash/.bytes，僅驗證傳輸 CRC")
    parser.add_argument("--json", action="store_true",
                        help="僅輸出非敏感版號、長度與摘要")
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="各項官方 HTTPS 公開資料請求的逾時秒數（1～60）")
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 60:
        parser.error("--timeout 必須介於 1 到 60 秒")
    if not args.online:
        parser.error("必須明確加上 --online，才會讀取官方公開版本")
    try:
        # 合併版本與 Manifest 流程，避免兩次完整查詢重複請求。
        # BAT 啟動使用 3 秒/請求的上限，失敗仍可進入離線畫面。
        report = inspect(
            with_manifests=args.manifests,
            observer=lambda: observe_official_versions(
                fetcher=lambda url: fetch_public_bytes(url, timeout=args.timeout)),
            manifest_fetcher=lambda url, *, limit: fetch_public_bytes(
                url, limit=limit, timeout=args.timeout),
        )
    except OfficialVersionError as exc:
        # 只回報安全的錯誤分類；不輸出原始封包、帳密或遠端回應。
        parser.exit(1, "官方唯讀資源檢查失敗：" + str(exc) + "\n")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("官方公開 ExeVer：", report["exe_version"])
        print("官方公開 DataVer：", report["data_version"])
        for package, revision in report["package_versions"].items():
            print(package + "：", revision)
        if args.manifests:
            print("Manifest 傳輸檢查：通過（CRC32LE／SHA-256）")
            print("資源版本識別：", report["catalog_identity"])
        print("正式服登入／資源解碼：未驗收，不可使用")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
