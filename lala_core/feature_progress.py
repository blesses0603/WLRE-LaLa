"""27 個功能的可驗證完成狀態，避免 UI 將導覽入口誤標成可用。

「本機可用」僅指離線模組與測試，與正式伺服器 E2E 完全不同。
"""
from dataclasses import dataclass
from .features import FEATURES


@dataclass(frozen=True, slots=True)
class FeatureProgress:
    key: str
    title: str
    local_capability: str
    server_ready: bool = False
    real_server_tested: bool = False


_LOCAL = {
    "dashboard": "可讀取本機功能狀態",
    "accounts": "分流選擇、遮蔽密碼輸入、登入狀態機與會話安全控制；目前正式服協定未核對，禁止傳送帳密",
    "resources": "資源 SHA-256、官方 Manifest／YooAsset 全量索引唯讀解析（不可登入）",
    "battle": "權威回合的離線技能候選（不發送）",
    "battle_ai": "手動啟用條件的離線技能候選（不自動出招）",
    "chat": "唯讀已驗證通道事件紀錄",
    "guild": "唯讀已驗證公會通道事件紀錄",
    "settings": "UI 偏好白名單與安全存檔",
    "efficiency": "經驗效率與目標時間計算",
    "crafting": "材料預約與製作數量規劃",
    "inventory": "材料持有量與缺料核對",
    "expeditions": "遠征隊伍資格規劃",
    "world": "已驗證地圖資料的最短路徑規劃",
    "portals": "已驗證地圖連線路徑規劃",
    "logs": "診斷資料安全遮罩",
}
PROGRESS = {
    feature.key: FeatureProgress(
        feature.key,
        feature.title,
        _LOCAL.get(feature.key, "尚無實作；僅有操作入口"),
    )
    for feature in FEATURES
}


def report_lines() -> tuple[str, ...]:
    return tuple(
        f"{p.title}：{p.local_capability}；正式服：{'已驗收' if p.real_server_tested else '尚未驗收'}"
        for p in PROGRESS.values()
    )
