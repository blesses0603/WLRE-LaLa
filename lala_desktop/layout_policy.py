"""LaLa 桌面左右欄位配置：右側小地圖與事件／戰場採同一窄版。"""
from . import theme as t


def right_column_width(main_window_width: int) -> int:
    """將 1280px 版型的 350px 窄版右欄等比例套用於固定 16:9 主視窗。

    視窗大小由 window_policy 啟動時決定，此函式不因右側分頁切換而變動。
    """
    if main_window_width <= 0:
        raise ValueError("主視窗寬度必須為正整數")
    return max(1, round(main_window_width * t.RIGHT_COLUMN_WIDTH / t.WINDOW_SIZE[0]))
