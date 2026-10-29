"""Tk 虛擬顯示驗證官方資源工具需使用者點擊；不會在測試時發網路請求。"""
import os
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.name == "nt" or os.environ.get("DISPLAY"),
                     "需要 Windows 桌面或 xvfb-run")
class ResourceUISmokeTests(unittest.TestCase):
    def test_resource_tools_are_visible_but_not_automatically_executed(self):
        from lala_desktop.app import LaLaDesktop

        def all_children(parent):
            for widget in parent.winfo_children():
                yield widget
                yield from all_children(widget)

        with patch("lala_core.resource_inspector.observe_official_versions") as remote, \
             patch("lala_desktop.local_tools.probe_line") as tcp:
            root = LaLaDesktop()
            try:
                root.open_feature("resources")
                root.update()
                window = root._feature_windows["resources"]
                labels = [getattr(widget, "label", "")
                          for widget in all_children(window)]
                self.assertIn("查詢官方版本", labels)
                self.assertIn("驗證兩包 Manifest", labels)
                self.assertIn("測試遊戲伺服器 TCP", labels)
                self.assertFalse(remote.called, "UI 開啟不得自動連官方 CDN")
                tcp.assert_not_called()
                self.assertTrue(window.overrideredirect())
            finally:
                root.destroy()
