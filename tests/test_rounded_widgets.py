"""圓角幾何契約不需要顯示器；互動與渲染交給 Xvfb 煙霧測試。"""
import unittest
from lala_desktop.rounded_widgets import rounded_points


class RoundedGeometryTests(unittest.TestCase):
    def test_nonzero_radius_produces_multiple_corner_points(self):
        points = rounded_points(0, 0, 200, 100, 18)
        self.assertGreater(len(points), 8)
        self.assertTrue(all(-0.001 <= points[i] <= 200.001 for i in range(0, len(points), 2)))
        self.assertTrue(all(-0.001 <= points[i] <= 100.001 for i in range(1, len(points), 2)))

    def test_radius_is_clamped_to_small_view(self):
        points = rounded_points(0, 0, 20, 10, 999)
        self.assertTrue(all(0 <= points[i] <= 20 for i in range(0, len(points), 2)))
        self.assertTrue(all(0 <= points[i] <= 10 for i in range(1, len(points), 2)))

    def test_zero_radius_and_degenerate_dimensions(self):
        self.assertEqual(len(rounded_points(0, 0, 100, 80, 0)), 8)
        self.assertEqual(len(rounded_points(0, 0, 0, 0, 12)), 4)
