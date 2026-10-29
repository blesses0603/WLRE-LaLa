import unittest
from lala_core.features import BY_KEY
from lala_desktop import theme as desktop
from lala_android import theme as android


class ClassicInterfaceContractTests(unittest.TestCase):
    def test_classic_desktop_palette(self):
        self.assertEqual(desktop.BG, "#101c2b")
        self.assertEqual(desktop.PANEL, "#142638")
        self.assertEqual(desktop.CYAN, "#62c9e0")

    def test_navigation_keys_are_valid(self):
        for platform in (desktop, android):
            self.assertEqual(len(platform.QUICK_KEYS), len(set(platform.QUICK_KEYS)))
            self.assertTrue(all(key in BY_KEY for key in platform.QUICK_KEYS))

    def test_desktop_overview_sections(self):
        titles = [name for row in desktop.OVERVIEW_ROWS for name, _ in row]
        self.assertIn("角色與夥伴", titles)
        self.assertIn("自動戰鬥", titles)
        self.assertIn("經驗效率", titles)
        self.assertEqual(len(titles), 10)
        self.assertTrue(all(key in BY_KEY for row in desktop.OVERVIEW_ROWS
                            for _, key in row))

    def test_mobile_card_radius(self):
        self.assertGreaterEqual(android.CARD_RADIUS, 16)
        self.assertGreaterEqual(android.WINDOW_RADIUS, 20)

    def test_desktop_dimensions(self):
        self.assertEqual(desktop.WINDOW_SIZE, (1280, 800))
        self.assertGreaterEqual(desktop.MAP_SIZE[0], 340)
