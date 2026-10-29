"""舊版 LaLa 按鈕美術：使用使用者舊版倉庫提供的 1262 原始 PNG。

普通／確認／停止：Btn_004／014／016，沿用 Unity 水平九宮格（34／37）。
視窗關閉與最小化：沿用舊版 button_art.py 的青色發光圓形圖樣。
功能快捷入口：使用 MainIcon 與 Btn_AI 圖片，圓形底板與舊版相同。
"""
from functools import lru_cache
from pathlib import Path
import tkinter as tk

from . import theme as t
from .rounded_widgets import RoundedButton

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageTk
except ImportError:  # 未安裝 Pillow 時 UI 仍可啟動，但按鈕退回可辨識的向量樣式。
    Image = ImageDraw = ImageEnhance = ImageFilter = ImageOps = ImageTk = None

ASSETS = Path(__file__).resolve().parent / "assets"
BUTTON_FILES = ("Btn_004", "Btn_014", "Btn_016", "Btn_Close04")
FUNCTION_ICONS = {
    "dashboard": "MainIcon_041",
    "party": "MainIcon_005",
    "companions": "MainIcon_010",
    "expeditions": "MainIcon_038",
    "alchemy": "MainIcon_007",
    "crafting": "MainIcon_011",
    "efficiency": "MainIcon_020",
    "battle_ai": "Btn_AI",
    "inventory": "MainIcon_001",
}


def pillow_available():
    return Image is not None


def button_kind(text, *, explicit=None):
    """與舊版 wlre/ui/button_art.py 的樣式分類一致。"""
    if explicit in ("Btn_004", "Btn_014", "Btn_016", "Btn_Minimize", "Btn_Close04"):
        return explicit
    if text in ("✕", "×"):
        return "Btn_Close04"
    if text in ("─", "－"):
        return "Btn_Minimize"
    title = str(text).strip()
    if title.startswith(("停止", "中斷", "取消")):
        return "Btn_016"
    if title.startswith(("啟動", "開始", "確認", "登入", "送出")):
        return "Btn_014"
    return "Btn_004"


@lru_cache(maxsize=12)
def source(name):
    if not pillow_available():
        return None
    if name in ("Btn_Minimize", "Btn_Close04"):
        # 舊版相同的發光外框及圖樣，避免不必要的系統字型差異。
        image = Image.new("RGBA", (198, 198))
        glow = Image.new("RGBA", image.size)
        draw = ImageDraw.Draw(glow)
        draw.ellipse((27, 27, 170, 170), outline=(55, 244, 239, 230), width=15)
        image = Image.alpha_composite(image, glow.filter(ImageFilter.GaussianBlur(12)))
        draw = ImageDraw.Draw(image)
        draw.ellipse((28, 28, 169, 169), fill=(25, 92, 101, 230),
                     outline=(169, 255, 250, 255), width=8)
        if name == "Btn_Minimize":
            draw.rounded_rectangle((61, 91, 137, 106), radius=5,
                                   fill=(230, 255, 255, 255))
        else:
            draw.line((72, 72, 126, 126), fill=(230, 255, 255, 255), width=13)
            draw.line((72, 126, 126, 72), fill=(230, 255, 255, 255), width=13)
        return image.resize((66, 66), Image.Resampling.LANCZOS)
    if name not in BUTTON_FILES:
        raise ValueError("不支援的舊版按鈕圖檔")
    with Image.open(ASSETS / "buttons" / (name + ".png")) as image:
        return image.convert("RGBA")


@lru_cache(maxsize=256)
def button_image(name, width, height, state="normal"):
    """保留 alpha、端點比例與 hover／pressed／disabled 圖像回饋。"""
    if not pillow_available():
        return None
    if width <= 0 or height <= 0:
        raise ValueError("無效按鈕尺寸")
    image = source(name)
    if name in ("Btn_Close04", "Btn_Minimize"):
        result = Image.new("RGBA", (width, height))
        icon = ImageOps.contain(image, (width, height), Image.Resampling.LANCZOS)
        result.alpha_composite(icon, ((width-icon.width)//2, (height-icon.height)//2))
    else:
        # 舊版 Unity SpriteAtlas 左右切片 34／37px；只拉伸中間，不拉伸圓弧兩端。
        scale = min(height/image.height, width/71)
        left = max(1, round(34*scale))
        right = max(1, round(37*scale))
        if left+right > width:
            left, right = width//2, width-width//2
        result = Image.new("RGBA", (width, height))
        for a, b, target_a, target_b in (
            (0, 34, 0, left),
            (34, image.width-37, left, width-right),
            (image.width-37, image.width, width-right, width),
        ):
            if target_b > target_a:
                part = image.crop((a, 0, b, image.height))
                part = part.resize((target_b-target_a, height), Image.Resampling.LANCZOS)
                result.alpha_composite(part, (target_a, 0))
    if state in ("active", "pressed"):
        alpha = result.getchannel("A")
        result = ImageEnhance.Brightness(result).enhance(
            1.15 if state == "active" else .78)
        result.putalpha(alpha)
    elif state == "disabled":
        alpha = result.getchannel("A").point(lambda value: round(value*.75))
        result = ImageOps.grayscale(result).convert("RGBA")
        result.putalpha(alpha)
    return result


@lru_cache(maxsize=20)
def icon_image(key, size=34):
    if not pillow_available() or key not in FUNCTION_ICONS:
        return None
    name = FUNCTION_ICONS[key]
    scale = 3
    image = Image.new("RGBA", (size*scale, size*scale))
    draw = ImageDraw.Draw(image)
    draw.ellipse((2, 2, size*scale-3, size*scale-3), fill=(45, 81, 101, 230),
                 outline=(180, 225, 235, 235), width=scale)
    with Image.open(ASSETS / "function-icons" / (name + ".png")) as source_image:
        glyph = ImageOps.contain(
            source_image.convert("RGBA"), (size*scale-20, size*scale-20),
            Image.Resampling.LANCZOS)
    image.alpha_composite(glyph, ((image.width-glyph.width)//2,
                                 (image.height-glyph.height)//2))
    return image.resize((size, size), Image.Resampling.LANCZOS)


def icon_photo(master, key, size=34):
    picture = icon_image(key, size)
    return ImageTk.PhotoImage(picture, master=master) if picture is not None else None


class SpriteButton(RoundedButton):
    """保留既有 Canvas 按鈕回呼／鍵盤操作，改由舊版 PNG 貼圖繪製背景。"""

    def __init__(self, parent, text, command, *, width=None, emphasis=False,
                 height=32, kind=None):
        self.kind = button_kind(text, explicit=kind)
        self._photo = None
        self._photo_cache = {}
        super().__init__(parent, text, command, width=width,
                         emphasis=emphasis, height=height)

    def _paint(self, _event=None):
        if not pillow_available():
            return super()._paint(_event)
        width, height = self.winfo_width(), self.winfo_height()
        if width <= 2 or height <= 2:
            width, height = int(self.cget("width")), int(self.cget("height"))
        state = ("disabled" if not self._enabled else
                 "pressed" if self._pressed else
                 "active" if self._hover or self.focus_get() is self else
                 "normal")
        key = (width, height, state)
        photo = self._photo_cache.get(key)
        if photo is None:
            photo = ImageTk.PhotoImage(
                button_image(self.kind, width, height, state), master=self)
            if len(self._photo_cache) > 12:
                self._photo_cache.clear()
            self._photo_cache[key] = photo
        self._photo = photo
        self.delete("all")
        self.create_image(0, 0, image=photo, anchor="nw", tags=("round-button", "legacy-sprite"))
        if self.kind not in ("Btn_Close04", "Btn_Minimize"):
            self.create_text(width/2, height/2, text=self.label,
                             font=("Microsoft JhengHei UI", 10, "bold"),
                             fill="#102c38" if self._enabled else t.DISABLED,
                             tags=("round-button-label",))
