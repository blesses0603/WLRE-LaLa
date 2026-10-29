"""LaLa P0 桌面 UI。所有資料都是明確標示的離線設計預覽。"""
import tkinter as tk
from tkinter import ttk

from lala_core.features import BY_KEY, FEATURES
from .version import DESKTOP_VERSION

BG = '#090f20'
SIDE = '#101b30'
CARD = '#182742'
BORDER = '#2c4366'
ACCENT = '#51bdff'
TEXT = '#eef6ff'
MUTED = '#a6bedb'
GOOD = '#68e2cc'
WARN = '#f8c677'


class LaLaDesktop(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f'LaLa Next — {DESKTOP_VERSION}｜UI 預覽')
        self.geometry('1240x790')
        self.minsize(960, 640)
        self.configure(bg=BG)
        self._filtered = []
        self._search = tk.StringVar()
        self._selected = 'dashboard'
        self._build()
        self._refresh_navigation()
        self.open_feature('dashboard')

    @staticmethod
    def label(parent, text, *, size=12, color=TEXT, weight='normal', bg=None, **kw):
        return tk.Label(parent, text=text, font=('Microsoft JhengHei UI', size, weight),
                        fg=color, bg=bg or parent.cget('bg'), **kw)

    def _build(self):
        top = tk.Frame(self, bg=SIDE, height=76, highlightbackground=BORDER, highlightthickness=1)
        top.pack(fill='x')
        top.pack_propagate(False)
        brand = tk.Frame(top, bg=SIDE)
        brand.pack(side='left', padx=24, pady=13)
        self.label(brand, '✦  LaLa', size=23, weight='bold', color=ACCENT).pack(anchor='w')
        self.label(brand, 'NEXT GENERATION  ·  UI PREVIEW', size=9, color=MUTED).pack(anchor='w')
        self.label(top, '●  離線  ·  尚未連線至遊戲伺服器', size=11,
                   color=WARN).pack(side='right', padx=27)

        body = tk.Frame(self, bg=BG)
        body.pack(fill='both', expand=True)

        nav = tk.Frame(body, bg=SIDE, width=263, highlightbackground=BORDER, highlightthickness=1)
        nav.pack(side='left', fill='y')
        nav.pack_propagate(False)
        self.label(nav, '功能導覽', size=13, weight='bold').pack(anchor='w', padx=20, pady=(24, 8))
        entry = tk.Entry(nav, textvariable=self._search, bg=CARD, fg=TEXT, insertbackground=TEXT,
                         relief='flat', font=('Microsoft JhengHei UI', 11),
                         highlightthickness=1, highlightbackground=BORDER,
                         highlightcolor=ACCENT)
        entry.pack(fill='x', padx=16, ipady=10)
        self._search.trace_add('write', lambda *_: self._refresh_navigation())
        self.label(nav, f'功能模組  ·  {len(FEATURES)} 項（未接入）', size=10, color=MUTED).pack(
            anchor='w', padx=20, pady=(19, 10))
        list_frame = tk.Frame(nav, bg=SIDE)
        list_frame.pack(fill='both', expand=True, padx=(12, 6), pady=(0, 14))
        self.nav_list = tk.Listbox(list_frame, bg=SIDE, fg=TEXT, selectbackground=CARD,
                                   selectforeground=ACCENT, activestyle='none', highlightthickness=0,
                                   borderwidth=0, font=('Microsoft JhengHei UI', 11),
                                   relief='flat', exportselection=False)
        sc = ttk.Scrollbar(list_frame, orient='vertical', command=self.nav_list.yview)
        self.nav_list.configure(yscrollcommand=sc.set)
        sc.pack(side='right', fill='y')
        self.nav_list.pack(side='left', fill='both', expand=True)
        self.nav_list.bind('<<ListboxSelect>>', self._on_select)
        self.label(nav, f'Desktop {DESKTOP_VERSION}  ·  開發預覽', size=10, color=MUTED).pack(
            anchor='w', padx=20, pady=(0, 20))

        self.content = tk.Frame(body, bg=BG)
        self.content.pack(side='left', fill='both', expand=True, padx=28, pady=23)

    def _refresh_navigation(self):
        term = self._search.get().strip().casefold()
        self._filtered = [f for f in FEATURES if not term or term in f.title.casefold() or term in f.group.casefold()]
        self.nav_list.delete(0, 'end')
        for feature in self._filtered:
            self.nav_list.insert('end', f'  ▸  {feature.title}')
        for index, feature in enumerate(self._filtered):
            if feature.key == self._selected:
                self.nav_list.selection_set(index)
                self.nav_list.see(index)
                break

    def _on_select(self, _event):
        selected = self.nav_list.curselection()
        if selected:
            self.open_feature(self._filtered[selected[0]].key, sync_nav=False)

    def _clear(self):
        for child in self.content.winfo_children():
            child.destroy()

    def open_feature(self, key, *, sync_nav=True):
        if key not in BY_KEY:
            return
        self._selected = key
        if sync_nav:
            self._refresh_navigation()
        self._clear()
        feature = BY_KEY[key]
        self.label(self.content, f'LaLa Next  /  {feature.group}', size=10, color=MUTED).pack(anchor='w')
        self.label(self.content, feature.title, size=27, weight='bold').pack(anchor='w', pady=(9, 3))
        self.label(self.content, feature.description, size=12, color=MUTED, wraplength=740,
                   justify='left').pack(anchor='w', pady=(0, 22))
        if key == 'dashboard':
            self._dashboard()
        else:
            self._placeholder(feature)

    def _dashboard(self):
        bar = tk.Frame(self.content, bg=BG)
        bar.pack(fill='x', pady=(0, 16))
        for title, value, note in (
            ('帳號連線', '0', '沒有建立任何遊戲連線'),
            ('執行中操作', '0', '未啟用自動化'),
            ('官方資源', '未驗證', '尚未下載或解析資料')):
            item = tk.Frame(bar, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
            item.pack(side='left', fill='both', expand=True, padx=(0, 10), ipady=12)
            self.label(item, title, color=MUTED, size=10).pack(anchor='w', padx=15, pady=(12, 5))
            self.label(item, value, size=21, weight='bold', color=GOOD if value == '0' else WARN).pack(anchor='w', padx=15)
            self.label(item, note, size=9, color=MUTED, wraplength=180, justify='left').pack(
                anchor='w', padx=15, pady=(4, 10))
        self.label(self.content, '核心功能入口', size=16, weight='bold').pack(anchor='w', pady=(10, 11))
        shortcuts = tk.Frame(self.content, bg=BG)
        shortcuts.pack(fill='x')
        for row, keys in enumerate((('accounts', 'battle', 'world'), ('inventory', 'expeditions', 'dungeons'))):
            line = tk.Frame(shortcuts, bg=BG)
            line.pack(fill='x', pady=(0, 12))
            for key in keys:
                feat = BY_KEY[key]
                tile = tk.Frame(line, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
                tile.pack(side='left', fill='both', expand=True, padx=(0, 10))
                tk.Button(tile, text=f'◈  {feat.title}', command=lambda k=key: self.open_feature(k),
                          anchor='w', bg=CARD, activebackground=BORDER, fg=TEXT,
                          activeforeground=ACCENT, bd=0, cursor='hand2', padx=14, pady=12,
                          font=('Microsoft JhengHei UI', 12, 'bold')).pack(fill='x')
                self.label(tile, '介面入口  ·  尚未接入', color=MUTED, size=9).pack(anchor='w', padx=16, pady=(0, 12))
        self._notice('此版本是 UI 開發骨架，所有遊戲操作均未啟用。正式登入與官方資源驗證屬後續階段。')

    def _placeholder(self, feature):
        frame = tk.Frame(self.content, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        frame.pack(fill='x', pady=(4, 14), ipady=17)
        self.label(frame, '◇  功能開發佔位頁', size=17, weight='bold', color=ACCENT).pack(
            anchor='w', padx=22, pady=(16, 10))
        self.label(frame, f'功能：{feature.title}', size=12).pack(anchor='w', padx=22, pady=4)
        self.label(frame, '目前狀態：僅有導航與畫面骨架；尚無真實遊戲功能。', size=11,
                   color=WARN, wraplength=650, justify='left').pack(anchor='w', padx=22, pady=5)
        self.label(frame, f'舊版參考責任區域：{feature.legacy_area}', size=10, color=MUTED,
                   wraplength=650, justify='left').pack(anchor='w', padx=22, pady=(7, 16))
        self._notice('安全限制：沒有遊戲伺服器連線、不讀取密碼、不發送任何封包。')
        tk.Button(self.content, text='← 返回主控台', command=lambda: self.open_feature('dashboard'),
                  bg=CARD, fg=TEXT, activebackground=BORDER, activeforeground=ACCENT,
                  relief='flat', cursor='hand2', padx=16, pady=9,
                  font=('Microsoft JhengHei UI', 11)).pack(anchor='w', pady=12)

    def _notice(self, message):
        frame = tk.Frame(self.content, bg=SIDE, highlightbackground=BORDER, highlightthickness=1)
        frame.pack(fill='x', pady=(14, 0))
        self.label(frame, 'ⓘ  ' + message, size=11, color=MUTED, wraplength=680,
                   justify='left').pack(anchor='w', padx=16, pady=16)


def main():
    try:
        app = LaLaDesktop()
    except tk.TclError as exc:
        raise SystemExit(f'無法開啟 LaLa 桌面視窗，請檢查 Tkinter 與圖形桌面環境：{exc}') from exc
    app.mainloop()
