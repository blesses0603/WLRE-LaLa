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
    "accounts": "Windows 可手動同意 XOR 舊版登入試驗；正式服身分／協定與 Android 登入仍未驗證",
    "resources": "資源 SHA-256、官方 Manifest／YooAsset 全量索引唯讀解析（不可登入）",
    "characters": "S3-1 試驗解析；S8-1 定長唯讀證據，不是權威屬性同步",
    "companions": "S8-2 舊版定長唯讀證據，不是夥伴同步",
    "party": "S13-4 舊版隊伍事件僅核對資料長度，未接通操作",
    "coop": "S186-6 舊版協力事件僅核對資料長度，不自動回覆",
    "dungeons": "S85-15 舊版副本結束事件僅核對資料長度",
    "battle": "權威回合的離線技能候選；S52-1 僅核對舊版封包長度（不發送）",
    "battle_ai": "手動啟用條件的離線技能候選（不自動出招）",
    "chat": "離線已驗證通道歷史；S1-1 舊版社交事件僅核對長度",
    "guild": "唯讀公會通道記錄；S39-60 只列舊版候選，不解析個資",
    "settings": "UI 偏好白名單與安全存檔",
    "efficiency": "經驗效率與目標時間計算",
    "crafting": "材料預約與製作數量規劃",
    "inventory": "離線材料缺料核對；S26-4 舊版金幣事件僅核對長度",
    "expeditions": "離線遠征資格規劃；S31-12 舊版狀態事件僅核對長度",
    "world": "本機最短路徑規劃；S6-1 舊版移動事件僅核對尺寸",
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
