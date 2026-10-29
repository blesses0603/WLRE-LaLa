"""可選 Kivy UI 預覽。沒有背景服務、連線、權限或真實帳號資料。"""
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.utils import get_color_from_hex
from lala_core.features import FEATURES
from .version import ANDROID_VERSION

BG = '#090F20'
CARD = '#182742'
TEXT = '#EEF6FF'


class LaLaAndroidPreview(App):
    title = 'LaLa Next UI 預覽'

    def build(self):
        root = BoxLayout(orientation='vertical', spacing=8, padding=12)
        from kivy.core.window import Window
        Window.clearcolor = get_color_from_hex(BG)
        root.add_widget(Label(text=f'LaLa Next · Android {ANDROID_VERSION}', font_size='21sp', bold=True,
                              size_hint_y=None, height=54, color=get_color_from_hex(TEXT)))
        self.detail = Label(text='離線 UI 預覽｜尚未實作伺服器連線', font_size='13sp',
                            size_hint_y=None, height=65, color=get_color_from_hex('#f8c677'))
        root.add_widget(self.detail)
        scroll = ScrollView(do_scroll_x=False)
        contents = BoxLayout(orientation='vertical', size_hint_y=None, spacing=6)
        contents.bind(minimum_height=contents.setter('height'))
        for feature in FEATURES:
            b = Button(text=f'{feature.group}  /  {feature.title}', size_hint_y=None, height=54,
                       background_normal='', background_color=get_color_from_hex(CARD),
                       color=get_color_from_hex(TEXT), font_size='16sp')
            b.bind(on_release=lambda _btn, f=feature: self.select(f))
            contents.add_widget(b)
        scroll.add_widget(contents)
        root.add_widget(scroll)
        return root

    def select(self, feature):
        self.detail.text = f'{feature.title}：尚未接入（不會送出遊戲封包）'


def run_app():
    LaLaAndroidPreview().run()
