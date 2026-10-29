"""需 DISPLAY／Xvfb 的實際 Tk 初始化與視窗導航測試。"""
import os
import unittest

@unittest.skipUnless(os.name == "nt" or os.environ.get("DISPLAY"),
                     "缺少圖形桌面；須以 xvfb-run 或 Windows 啟動")
class DesktopSmokeTests(unittest.TestCase):
    def test_classic_dashboard_and_feature_windows(self):
        from lala_desktop.app import LaLaDesktop
        root = LaLaDesktop()
        try:
            root.update_idletasks()
            root.update()
            self.assertTrue(root._map_canvas.winfo_exists())
            self.assertTrue(root._events.winfo_exists())
            self.assertEqual(root.winfo_width(), 1280)
            self.assertEqual(root.winfo_height(), 800)
            root.open_feature("expeditions")
            root.update()
            self.assertTrue(root._feature_windows["expeditions"].winfo_exists())
            root._show_all_features()
            root.update()
            self.assertTrue(root._feature_windows["_catalog"].winfo_exists())
        finally:
            root.destroy()
