"""右欄固定採使用者截圖的窄版，與分頁狀態無關。"""
import unittest
from lala_desktop import theme as t
from lala_desktop.layout_policy import right_column_width
from lala_desktop.window_policy import MAIN_PRESETS


class RightColumnLayoutTests(unittest.TestCase):
    def test_reference_narrow_column_width(self):
        self.assertEqual(t.RIGHT_COLUMN_WIDTH, 350)
        self.assertEqual(right_column_width(1280), 350)

    def test_proportional_fixed_right_column(self):
        for width, _height in MAIN_PRESETS:
            with self.subTest(width=width):
                right = right_column_width(width)
                self.assertGreater(right, 0)
                self.assertLess(right, width)
                self.assertAlmostEqual(right / width, 350 / 1280, delta=.001)
                self.assertLess(right / width, 0.3)

    def test_zero_width_rejected(self):
        with self.assertRaises(ValueError):
            right_column_width(0)
