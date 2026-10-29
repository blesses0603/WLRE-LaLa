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
        self.assertTrue(window.overrideredirect(), "不得顯示作業系統原生標題列")

    def test_main_and_all_feature_windows_fixed_16_by_9(self):
        from lala_desktop.app import LaLaDesktop
        root = LaLaDesktop()
        try:
            self._assert_fixed(root, kind="main")
            self.assertTrue(root._map_canvas.winfo_exists())
            self.assertEqual(len(root._map_canvas.find_withtag("map-rounded-surface")), 1)
            from lala_desktop.rounded_widgets import RoundedPanel
            from lala_desktop.game_buttons import SpriteButton, pillow_available
            self.assertIsInstance(root._top, RoundedPanel)
            self.assertIsInstance(root._minimize_button, SpriteButton)
            self.assertEqual(len(root._top.canvas.find_withtag("round")), 1)
            self.assertEqual(len(root._minimize_button.find_withtag("round-button")), 1)
            if pillow_available():
                self.assertEqual(len(root._minimize_button.find_withtag("legacy-sprite")), 1)
                self.assertEqual(root._close_button.kind, "Btn_Close04")
                self.assertEqual(root._minimize_button.kind, "Btn_Minimize")
            root._show_right_tab("battle")
            self.assertTrue(root._right_pages["battle"].winfo_manager())
            root._show_right_tab("events")
            self.assertTrue(root._right_pages["events"].winfo_manager())
            self.assertTrue(root._minimize_button.winfo_exists())
            self.assertTrue(root._close_button.winfo_exists())
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
