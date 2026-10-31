"""模擬 BAT 傳入的自檢結果，驗證首頁狀態；不可自動連網或解鎖登入。"""
import os
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.name == "nt" or os.environ.get("DISPLAY"),
                     "需要 Windows 桌面或 xvfb-run")
class StartupBannerTests(unittest.TestCase):
    def test_displays_preflight_result_without_changing_ui_layout(self):
        import tkinter as tk
        from lala_desktop.app import LaLaDesktop

        def labels(parent):
            for child in parent.winfo_children():
                if isinstance(child, tk.Label):
                    yield child.cget("text")
                yield from labels(child)

        scenarios = [
            ("transport_checked", "自檢通過／離線", "正式服協定尚未驗證"),
            ("installed", "資源已安裝／離線", "LaLa 所需 Bundle 已安裝驗證"),
            ("failed", "自檢失敗／離線", "官方資源自檢未通過"),
            ("not_checked", "尚未自檢／離線", "未執行官方資源自檢"),
        ]
        for value, badge, explanation in scenarios:
            with self.subTest(status=value), patch.dict(
                    os.environ, {"LALA_STARTUP_RESOURCE_STATUS": value}):
                root = LaLaDesktop()
                try:
                    root.update()
                    texts = list(labels(root))
                    self.assertTrue(any(badge in x for x in texts), texts[:25])
                    self.assertTrue(any(explanation in x for x in texts), texts[:25])
                    self.assertFalse(root._chrome is None)
                finally:
                    root.destroy()

    def test_invalid_environment_value_fails_closed(self):
        from lala_desktop.app import LaLaDesktop
        with patch.dict(os.environ, {"LALA_STARTUP_RESOURCE_STATUS": "trusted_login"}):
            root = LaLaDesktop()
            try:
                self.assertEqual(root._startup_resource_status, "not_checked")
            finally:
                root.destroy()
