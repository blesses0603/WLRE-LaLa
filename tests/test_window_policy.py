"""離線驗證所有桌面視窗的 16:9 固定尺寸策略。"""
import unittest

from lala_desktop import theme
from lala_desktop.window_policy import (
    MAIN_PRESETS, DIALOG_PRESETS, choose_size, is_16_by_9,
)


class WindowPolicyTests(unittest.TestCase):
    def test_all_fixed_dimensions_are_16_by_9(self):
        for size in (theme.WINDOW_SIZE, theme.DIALOG_SIZE, *MAIN_PRESETS, *DIALOG_PRESETS):
            with self.subTest(size=size):
                self.assertTrue(is_16_by_9(size))

    def test_preferred_sizes_on_large_monitor(self):
        self.assertEqual(choose_size("main", 1920, 1080), (1280, 720))
        self.assertEqual(choose_size("dialog", 1920, 1080), (800, 450))

    def test_small_monitor_uses_16_by_9_fallback(self):
        self.assertEqual(choose_size("main", 1366, 768), (1152, 648))
        self.assertEqual(choose_size("main", 1024, 700), (1024, 576))
        self.assertEqual(choose_size("dialog", 800, 540), (800, 450))
        self.assertTrue(is_16_by_9(choose_size("main", 800, 600)))

    def test_invalid_kind_or_non_widescreen(self):
        with self.assertRaises(ValueError):
            choose_size("unknown", 1920, 1080)
        self.assertFalse(is_16_by_9((1280, 800)))
        self.assertFalse(is_16_by_9((0, 720)))
