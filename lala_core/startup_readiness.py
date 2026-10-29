"""P1 啟動條件顯示：只讀版本／Manifest 不能使遊戲帳號登入。

接入正式 login 之前，必須另有經審核的 YooAsset parser、功能來源
schema、伺服器協定與端到端證據；不從 JSON 自行解鎖。
"""
from dataclasses import dataclass
from .manifest_transport import ManifestPair
from .official_versions import ObservedVersions, OfficialVersionError


@dataclass(frozen=True, slots=True)
class StartupReadiness:
    official_versions_observed: bool
    manifests_transport_checked: bool
    gameplay_catalog_validated: bool
    protocol_verified: bool
    can_login: bool
    reason: str


def review_startup(versions: ObservedVersions | None = None,
                   receipts: ManifestPair | None = None) -> StartupReadiness:
    if versions is None:
        if receipts is not None:
            raise OfficialVersionError("缺少資源版本觀察，不可接受 Manifest 收據")
        return StartupReadiness(False, False, False, False, False, "尚未觀察官方版本")
    if not isinstance(versions, ObservedVersions):
        raise OfficialVersionError("無效官方版本觀察")
    if receipts is None:
        return StartupReadiness(True, False, False, False, False,
                                "僅已觀察版本；尚未驗證兩份 Manifest")
    if not isinstance(receipts, ManifestPair):
        raise OfficialVersionError("無效 Manifest 身分")
    if (receipts.exe_version != versions.exe_version or
            receipts.data_version != versions.data_version or
            tuple((m.package, m.package_revision) for m in receipts.manifests) !=
            versions.package_versions):
        raise OfficialVersionError("Manifest 與最新版本觀察不一致，不可啟用")
    return StartupReadiness(True, True, False, False, False,
                            "Manifest 僅通過傳輸校驗；仍缺完整解析、資源相容與協定驗收")
