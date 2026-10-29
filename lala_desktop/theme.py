"""經典 LaLa 桌面 UI 設計規格（參照舊版 wlre/ui/theme.py）。"""

# 承襲舊版 EXP Monitor 青藍色玻璃風格，不依賴遊戲素材或 UI 套件。
BG = "#101c2b"
PANEL = "#142638"
SURFACE = "#112e40"
SURFACE_ACTIVE = "#233d52"
FIELD = "#16364b"
TEXT = "#eff7ff"
MUTED = "#a7cbdc"
CYAN = "#62c9e0"
SECTION = "#c5f1ff"
BORDER = "#397c98"
WARN = "#ffe2b0"
DISABLED = "#7292a4"

# 舊版 1280×800 主視窗；保留小地圖、戰場與聊天的固定位置概念。
WINDOW_SIZE = (1280, 800)
MIN_SIZE = (1060, 680)
MAP_SIZE = (350, 288)
QUICK_KEYS = (
    "dashboard", "party", "companions", "expeditions", "alchemy",
    "crafting", "efficiency", "battle_ai", "inventory",
)
OVERVIEW_ROWS = (
    (("角色與夥伴", "characters"), ("目前活動", "tent")),
    (("自動戰鬥", "battle_ai"), ("自動徘徊", "world"), ("遠征", "expeditions")),
    (("補給紀錄", "supplies"), ("煉金", "alchemy"), ("製作", "crafting")),
    (("隊伍檢查", "party"), ("經驗效率", "efficiency")),
)
