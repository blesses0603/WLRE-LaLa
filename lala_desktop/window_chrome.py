"""LaLa 無系統標題列視窗：關閉、移動、最小化及 Windows 工作列相容。

不改變視窗尺寸，也不管理遊戲連線。只讓綁定的空白頁首區可以拖曳。
"""
import sys


class BorderlessChrome:
    def __init__(self, window):
        self.window = window
        self._drag_origin = None
        self._awaiting_restore = False
        window.overrideredirect(True)
        window.bind("<Map>", self._on_map, add="+")
        # 在 Windows 上保留工作列／Alt+Tab 視窗入口（需原生 Win32；其他平台不修改）。
        if sys.platform == "win32":
            window.after_idle(self._register_win32_taskbar)

    def bind_drag(self, *widgets):
        """只綁在標題文字及其背景，避免攔截功能按鈕與輸入框。"""
        for widget in widgets:
            widget.configure(cursor="fleur")
            widget.bind("<ButtonPress-1>", self.start_drag, add="+")
            widget.bind("<B1-Motion>", self.drag, add="+")
            widget.bind("<ButtonRelease-1>", self.stop_drag, add="+")

    def start_drag(self, event):
        self._drag_origin = (
            event.x_root, event.y_root,
            self.window.winfo_x(), self.window.winfo_y(),
        )

    def drag(self, event):
        if self._drag_origin is None:
            return
        pointer_x, pointer_y, original_x, original_y = self._drag_origin
        dx, dy = event.x_root - pointer_x, event.y_root - pointer_y
        width, height = self.window.winfo_width(), self.window.winfo_height()
        sw, sh = self.window.winfo_screenwidth(), self.window.winfo_screenheight()
        new_x = max(0, min(original_x + dx, max(0, sw - width)))
        new_y = max(0, min(original_y + dy, max(0, sh - height)))
        self.window.geometry(f"+{new_x}+{new_y}")

    def stop_drag(self, _event=None):
        self._drag_origin = None

    def minimize(self):
        """暫時解除 override-redirect，才能使用視窗管理器的 iconify。"""
        self.stop_drag()
        self._awaiting_restore = True
        self.window.overrideredirect(False)
        self.window.update_idletasks()
        self.window.iconify()

    def _on_map(self, event):
        if event.widget is not self.window or not self._awaiting_restore:
            return
        self._awaiting_restore = False
        self.window.after_idle(self._restore_borderless)

    def _restore_borderless(self):
        try:
            if not self.window.winfo_exists():
                return
            self.window.overrideredirect(True)
            if sys.platform == "win32":
                self._register_win32_taskbar()
        except Exception:
            # 視窗可能在還原事件與 after_idle 間被使用者關閉。
            if self.window.winfo_exists():
                raise

    def _register_win32_taskbar(self):
        """移除工具視窗樣式，使用 Windows 工作列與 Alt+Tab 顯示主視窗。

        Windows 平台細節需在 Windows 11 實機確認：Tk 的 HWND wrapper 可能
        隨 Tk 版本和 iconify/restore 時機改變。
        """
        if not self.window.winfo_exists():
            return
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.GetParent.argtypes = (wintypes.HWND,)
        user32.GetParent.restype = wintypes.HWND
        user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.SetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_long)
        user32.SetWindowLongW.restype = ctypes.c_long
        user32.SetWindowPos.argtypes = (
            wintypes.HWND, wintypes.HWND,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint,
        )
        user32.SetWindowPos.restype = wintypes.BOOL

        hwnd = user32.GetParent(self.window.winfo_id()) or self.window.winfo_id()
        GWL_EXSTYLE = -20
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_APPWINDOW = 0x00040000
        exstyle = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        desired = (exstyle | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
        if desired != exstyle:
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, desired)
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOZORDER = 0x0004
            SWP_FRAMECHANGED = 0x0020
            user32.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0,
                SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED,
            )


def install_borderless(window):
    """一個視窗只建立一份 ChromeController，防止重複綁定 Map。"""
    chrome = getattr(window, "_lala_borderless", None)
    if chrome is None:
        chrome = BorderlessChrome(window)
        window._lala_borderless = chrome
    return chrome
