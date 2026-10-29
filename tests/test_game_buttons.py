"""舊版美術資源完整性、按鈕分類與原始圖片縮放規則。"""
import unittest
from lala_desktop.game_buttons import (
    ASSETS, BUTTON_FILES, FUNCTION_ICONS, button_kind, button_image, icon_image,
    pillow_available,
)


class LegacyButtonTests(unittest.TestCase):
    def test_source_files_exist(self):
        for name in BUTTON_FILES:
            self.assertTrue((ASSETS/"buttons"/(name+".png")).is_file(), name)
        for name in FUNCTION_ICONS.values():
            self.assertTrue((ASSETS/"function-icons"/(name+".png")).is_file(), name)

    def test_legacy_text_styles(self):
        cases = {
            "開啟": "Btn_004", "全部功能": "Btn_004",
            "登入／選角": "Btn_014", "確認": "Btn_014",
            "開始": "Btn_014", "送出": "Btn_014",
            "停止": "Btn_016", "中斷連線": "Btn_016", "取消": "Btn_016",
            "─": "Btn_Minimize", "✕": "Btn_Close04",
        }
        for label, expected in cases.items():
            with self.subTest(label=label):
                self.assertEqual(button_kind(label), expected)

    @unittest.skipUnless(pillow_available(), "未安裝 Pillow")
    def test_nine_slice_preserves_requested_size(self):
        for kind in ("Btn_004", "Btn_014", "Btn_016"):
            for size in ((72, 32), (150, 42), (250, 48)):
                with self.subTest(kind=kind, size=size):
                    picture = button_image(kind, *size)
                    self.assertEqual(picture.size, size)
                    self.assertGreater(picture.getchannel("A").getextrema()[1], 0)

    @unittest.skipUnless(pillow_available(), "未安裝 Pillow")
    def test_icon_images_match_legacy_dimensions(self):
        for key in FUNCTION_ICONS:
            image = icon_image(key, 34)
            self.assertEqual(image.size, (34, 34))

    @unittest.skipUnless(pillow_available(), "未安裝 Pillow")
    def test_disabled_sprite_alpha_is_lower(self):
        normal = button_image("Btn_004", 140, 36, "normal")
        disabled = button_image("Btn_004", 140, 36, "disabled")
        self.assertLess(sum(disabled.getchannel("A").getdata()),
                        sum(normal.getchannel("A").getdata()))
