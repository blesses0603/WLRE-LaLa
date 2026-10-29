"""Windows 視窗圓角裁切：僅 Windows 11／Win32 可真正裁切外框。

成功的 SetWindowRgn 會接管 region 所有權，不能再 DeleteObject。
失敗時退回正常無邊框視窗，保留關閉／最小化功能。
"""
import sys


def apply_windows_rounded_region(window, *, radius=20):
    if sys.platform != "win32" or not window.winfo_exists():
        return False
    import ctypes
    from ctypes import wintypes

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    user32.GetParent.argtypes = (wintypes.HWND,)
    user32.GetParent.restype = wintypes.HWND
    user32.SetWindowRgn.argtypes = (wintypes.HWND, wintypes.HRGN, wintypes.BOOL)
    user32.SetWindowRgn.restype = ctypes.c_int
    gdi32.CreateRoundRectRgn.argtypes = (
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int,
    )
    gdi32.CreateRoundRectRgn.restype = wintypes.HRGN
    gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
    gdi32.DeleteObject.restype = wintypes.BOOL

    hwnd = user32.GetParent(window.winfo_id()) or window.winfo_id()
    width, height = window.winfo_width(), window.winfo_height()
    if width < 2 or height < 2:
        return False
    ellipse = max(2, int(radius)*2)
    region = gdi32.CreateRoundRectRgn(0, 0, width+1, height+1, ellipse, ellipse)
    if not region:
        return False
    if not user32.SetWindowRgn(hwnd, region, True):
        gdi32.DeleteObject(region)
        return False
    return True
