"""Android P0 經典 LaLa UI 預覽：不連線、不啟動背景服務。"""
from kivy.app import App
from kivy.graphics import Color, Ellipse, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window
from kivy.utils import get_color_from_hex

from lala_core.features import BY_KEY, FEATURES
from lala_core.feature_progress import PROGRESS
from . import theme as t
from .version import ANDROID_VERSION


def rgba(hex_color):
    return get_color_from_hex(hex_color)


def surface(view, *, fill=t.PANEL, border=t.BORDER, radius=t.CARD_RADIUS):
    """跟隨尺寸更新的圓角面板。"""
    with view.canvas.before:
        Color(*rgba(border))
        outer = RoundedRectangle(pos=view.pos, size=view.size, radius=[dp(radius)])
        Color(*rgba(fill))
        inner = RoundedRectangle(pos=view.pos, size=view.size, radius=[dp(max(1, radius-1))])
    def resize(*_):
        outer.pos, outer.size = view.pos, view.size
        inner.pos = (view.x + dp(1), view.y + dp(1))
        inner.size = (max(dp(1), view.width - dp(2)), max(dp(1), view.height - dp(2)))
    view.bind(pos=resize, size=resize)
    resize()
    return view


def caption(value, *, size=14, color=t.TEXT, height=34, bold=False):
    widget = Label(text=value, font_size=f"{size}sp", bold=bold, color=rgba(color),
                   size_hint_y=None, height=dp(height), halign="left", valign="middle")
    widget.bind(size=lambda w, _: setattr(w, "text_size", (w.width-dp(10), w.height)))
    return widget


def classic_button(value, on_release, *, height=48):
    item = Button(text=value, size_hint_y=None, height=dp(height),
                  background_normal="", background_down="", background_color=(0, 0, 0, 0),
                  color=rgba(t.TEXT), font_size="13sp")
    surface(item, fill=t.SOFT, radius=15)
    item.bind(on_release=lambda *_: on_release())
    return item


class QuickTile(ButtonBehavior, BoxLayout):
    """舊版 Android 圓形圖示入口。P0 尚無官方貼圖，使用文字佔位。"""
    def __init__(self, feature, callback, **kwargs):
        super().__init__(orientation="vertical", size_hint=(None, None),
                         size=(dp(76), dp(76)), padding=[dp(3), dp(2)], **kwargs)
        with self.canvas.before:
            Color(*rgba(t.BORDER))
            circle = Ellipse()
            Color(*rgba(t.SOFT))
            inside = Ellipse()
        def resize(*_):
            x = self.x + (self.width-dp(46))/2
            y = self.top - dp(49)
            circle.pos, circle.size = (x, y), (dp(46), dp(46))
            inside.pos, inside.size = (x+dp(2), y+dp(2)), (dp(42), dp(42))
        self.bind(pos=resize, size=resize)
        resize()
        title = Label(text=feature.title[:2], color=rgba(t.TEXT), bold=True,
                      font_size="12sp", size_hint_y=None, height=dp(45))
        name = Label(text=feature.title.replace("管理", "").replace("控制", "")[:6],
                     color=rgba(t.MUTED), font_size="10sp", size_hint_y=None,
                     height=dp(25), halign="center", valign="middle")
        name.bind(size=lambda w, _: setattr(w, "text_size", (w.width, w.height)))
        self.add_widget(title)
        self.add_widget(name)
        self.bind(on_release=lambda *_: callback(feature.key))


class LaLaAndroidPreview(App):
    title = "LaLa ｜經典手機介面"

    def build(self):
        Window.clearcolor = rgba(t.BG)
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(9))
        header = surface(BoxLayout(orientation="vertical", size_hint_y=None,
                                   height=dp(82), padding=[dp(15), dp(8)]),
                         radius=t.WINDOW_RADIUS)
        header.add_widget(caption(f"✦  LaLa｜飄流幻境 RE   {ANDROID_VERSION}",
                                  size=17, color=t.CYAN, height=34, bold=True))
        header.add_widget(caption("● 離線預覽  ·  角色／伺服器尚未同步",
                                  size=12, color=t.WARN, height=27))
        root.add_widget(header)
        quick = ScrollView(do_scroll_y=False, do_scroll_x=True, bar_width=dp(2),
                           size_hint_y=None, height=dp(80))
        links = BoxLayout(orientation="horizontal", size_hint_x=None,
                          width=dp(78)*len(t.QUICK_KEYS), spacing=dp(2))
        for key in t.QUICK_KEYS:
            links.add_widget(QuickTile(BY_KEY[key], self.select))
        quick.add_widget(links)
        root.add_widget(quick)
        status = surface(BoxLayout(orientation="vertical", size_hint_y=None,
                                   height=dp(56), padding=[dp(12), dp(3)]),
                         fill=t.SOFT, radius=14)
        self.status_label = caption("等待登入｜沒有任何遊戲封包或自動操作",
                                    size=12, color=t.MUTED, height=48)
        status.add_widget(self.status_label)
        root.add_widget(status)
        scroll = ScrollView(do_scroll_x=False, do_scroll_y=True, bar_width=dp(3))
        self.main_column = BoxLayout(orientation="vertical", size_hint_y=None,
                                     spacing=dp(9), padding=[dp(1), dp(6)])
        self.main_column.bind(minimum_height=self.main_column.setter("height"))
        scroll.add_widget(self.main_column)
        root.add_widget(scroll)
        self.select("dashboard")
        return root

    def _card(self, title, description, target=None):
        panel = surface(BoxLayout(orientation="vertical", size_hint_y=None,
                                  height=dp(107), padding=[dp(14), dp(10)], spacing=dp(4)))
        panel.add_widget(caption(title, size=14, color=t.CYAN, bold=True, height=30))
        panel.add_widget(caption(description, size=11, color=t.MUTED, height=34))
        if target is not None:
            button = classic_button("查看", lambda k=target: self.select(k), height=27)
            panel.height = dp(137)
            panel.add_widget(button)
        self.main_column.add_widget(panel)

    def select(self, key):
        if key not in BY_KEY:
            return
        feature = BY_KEY[key]
        self.main_column.clear_widgets()
        self.main_column.add_widget(caption(
            "主頁  /  經典介面" if key == "dashboard" else feature.title,
            size=18, color=t.TEXT, height=43, bold=True))
        if key == "dashboard":
            for title, note, target in (
                ("角色與夥伴", "角色資料待登入後同步", "characters"),
                ("目前活動", "離線；所有自動功能均未啟用", "tent"),
                ("自動戰鬥／自動徘徊", "等待遊戲會話與操作安全驗證", "battle_ai"),
                ("遠征", "遠征資料尚未同步", "expeditions"),
                ("包包與物品", "背包格位尚未同步", "inventory"),
                ("小地圖", "尚無官方場景／座標資料", "world"),
                ("事件紀錄／聊天", "尚無可顯示的伺服器訊息", "logs"),
            ):
                self._card(title, note, target)
            self.main_column.add_widget(classic_button(
                "全部功能（27）", self.show_all, height=52))
        else:
            self._card(feature.title, feature.description)
            progress = PROGRESS[key]
            # Shared core status, not a claim that Android has a network adapter.
            capability = progress.local_capability
            short = capability[:47] + ("…" if len(capability) > 47 else "")
            self._card("共用核心進度", short)
            self._card("Android 連線狀態", "尚未驗收｜不會傳送遊戲指令")
            self.main_column.add_widget(classic_button(
                "← 返回主頁", lambda: self.select("dashboard")))
            self.main_column.add_widget(classic_button("全部功能", self.show_all))
        self.status_label.text = "● 離線 UI 預覽｜所有操作均不會傳送遊戲封包"

    def show_all(self):
        self.main_column.clear_widgets()
        self.main_column.add_widget(caption("全部功能（27）", size=18, height=46,
                                            color=t.TEXT, bold=True))
        for feature in FEATURES:
            self.main_column.add_widget(classic_button(
                f"{feature.group}  /  {feature.title}",
                lambda k=feature.key: self.select(k)))
        self.main_column.add_widget(classic_button("← 返回主頁",
                                                    lambda: self.select("dashboard")))


def run_app():
    LaLaAndroidPreview().run()
