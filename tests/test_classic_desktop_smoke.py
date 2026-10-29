"""Xvfb／Windows：實際 Tk GUI 主視窗與各功能視窗固定 16:9 測試。"""
import os
import unittest

from lala_desktop.window_policy import choose_size, is_16_by_9


@unittest.skipUnless(os.name == "nt" or os.environ.get("DISPLAY"),
                     "缺少圖形桌面；須以 xvfb-run 或 Windows 啟動")
class DesktopSmokeTests(unittest.TestCase):
    def _assert_fixed(self, window, *, kind):
        window.update_idletasks()
        window.update()
        actual = (window.winfo_width(), window.winfo_height())
        self.assertEqual(actual, choose_size(kind, window.winfo_screenwidth(),
                                            window.winfo_screenheight()))
        self.assertTrue(is_16_by_9(actual))
        self.assertEqual(tuple(window.resizable()), (0, 0))
        self.assertEqual(tuple(window.minsize()), actual)
        self.assertEqual(tuple(window.maxsize()), actual)

    def test_main_and_all_feature_windows_fixed_16_by_9(self):
        from lala_desktop.app import LaLaDesktop
        root = LaLaDesktop()
        try:
            self._assert_fixed(root, kind="main")
            self.assertTrue(root._map_canvas.winfo_exists())
            self.assertTrue(root._events.winfo_exists())

            root.open_feature("expeditions")
            self._assert_fixed(root._feature_windows["expeditions"], kind="dialog")
            root.open_feature("world")
            self._assert_fixed(root._feature_windows["world"], kind="dialog")
            root._show_all_features()
            catalog = root._feature_windows["_catalog"]
            self._assert_fixed(catalog, kind="dialog")

            # 單一功能只存在一個視窗；再次開啟不能產生可縮放的另一個。
            original = root._feature_windows["expeditions"]
            root.open_feature("expeditions")
            self.assertIs(root._feature_windows["expeditions"], original)
        finally:
            root.destroy()
