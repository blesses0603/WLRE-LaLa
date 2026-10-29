"""LaLa Desktop 視窗政策：所有主視窗及功能視窗固定 16:9、禁止縮放。

僅封裝 Tk window-manager 操作，不處理遊戲網路、狀態或核心資料。
Android 使用手機原生可用尺寸，並非可拖曳的桌面視窗。
"""
from . import theme as t

# 符合 16:9 的預設尺寸；僅在啟動時依螢幕可用空間選擇，不允許使用者再改。
MAIN_PRESETS = ((1280, 720), (1152, 648), (1024, 576), (960, 540), (800, 450))
DIALOG_PRESETS = ((800, 450), (768, 432), (640, 360))
TITLEBAR_AND_TASKBAR_RESERVE = 72


def is_16_by_9(size: tuple[int, int]) -> bool:
    width, height = size
    return width > 0 and height > 0 and width * 9 == height * 16


def choose_size(kind: str, screen_width: int, screen_height: int) -> tuple[int, int]:
    """挑選能容納於螢幕的固定 16:9 預設，避免最大視窗超出工作區高度。"""
    if kind == "main":
        candidates = MAIN_PRESETS
    elif kind == "dialog":
        candidates = DIALOG_PRESETS
    else:
        raise ValueError(f"不支援的視窗類型：{kind}")
    usable_height = max(0, screen_height - TITLEBAR_AND_TASKBAR_RESERVE)
    for size in candidates:
        if size[0] <= screen_width and size[1] <= usable_height:
            return size
    # 很小的螢幕仍使用最小 16:9 視窗，可能需要提高系統解析度。
    return candidates[-1]


def apply_fixed_window(window, *, kind: str, parent=None) -> tuple[int, int]:
    """鎖定尺寸與 16:9，停用桌面視窗管理器的使用者縮放及最大化功能。"""
    sw, sh = window.winfo_screenwidth(), window.winfo_screenheight()
    size = choose_size(kind, sw, sh)
    if not is_16_by_9(size):
        raise ValueError("視窗尺寸不是 16:9")
    width, height = size

    if parent is None:
        x = max(0, (sw - width) // 2)
        y = max(0, (sh - height - TITLEBAR_AND_TASKBAR_RESERVE) // 2)
    else:
        parent.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
        x = max(0, min(x, max(0, sw - width)))
        y = max(0, min(y, max(0, sh - height - TITLEBAR_AND_TASKBAR_RESERVE)))

    window.geometry(f"{width}x{height}+{x}+{y}")
    window.minsize(width, height)
    window.maxsize(width, height)
    window.resizable(False, False)
    return size
