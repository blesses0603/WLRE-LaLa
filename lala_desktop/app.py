"""LaLa P0 經典 UI：承襲舊版版面與操作節奏，所有畫面皆為離線預覽。"""
import tkinter as tk
from tkinter import font as tkfont, ttk

from lala_core.features import BY_KEY, FEATURES
from . import theme as t
from .version import DESKTOP_VERSION
from .window_policy import apply_fixed_window
from .window_chrome import install_borderless


class LaLaDesktop(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"LaLa — {DESKTOP_VERSION}｜經典介面預覽")
        apply_fixed_window(self, kind="main")
        self._chrome = install_borderless(self)
        self.configure(bg=t.BG)
        self._font = self._choose_font()
        self._feature_windows = {}
        self._configure_ttk()
        self._build()

    def _choose_font(self):
        families = set(tkfont.families(self))
        for name in ("Microsoft JhengHei UI", "Noto Sans CJK TC", "PingFang TC", "WenQuanYi Micro Hei"):
            if name in families:
                return name
        return tkfont.nametofont("TkDefaultFont", root=self).actual("family")

    def text(self, parent, value, *, size=11, color=t.TEXT, bold=False, **kwargs):
        return tk.Label(parent, text=value, font=(self._font, size, "bold" if bold else "normal"),
                        fg=color, bg=parent.cget("bg"), **kwargs)

    def _configure_ttk(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Classic.TNotebook", background=t.PANEL, borderwidth=0)
        s.configure("Classic.TNotebook.Tab", font=(self._font, 11), padding=(14, 7),
                    foreground=t.TEXT, background=t.SURFACE_ACTIVE)
        s.map("Classic.TNotebook.Tab", background=[("selected", t.SURFACE)],
              foreground=[("selected", t.CYAN)])
        s.configure("Classic.Vertical.TScrollbar", background=t.PANEL, troughcolor=t.BG)

    def _panel(self, parent, *, bg=t.PANEL, border=True):
        return tk.Frame(parent, bg=bg, highlightthickness=1 if border else 0,
                        highlightbackground=t.BORDER)

    def _button(self, parent, label, command, *, emphasis=False, width=None):
        return tk.Button(parent, text=label, command=command, width=width,
                         bg=t.SURFACE_ACTIVE if not emphasis else t.FIELD,
                         activebackground=t.SURFACE, fg=t.CYAN if emphasis else t.TEXT,
                         activeforeground=t.SECTION, relief="flat", bd=0,
                         font=(self._font, 10, "bold"), cursor="hand2",
                         padx=10, pady=6, takefocus=True,
                         highlightthickness=1, highlightbackground=t.BORDER)

    def _build(self):
        self._top = self._panel(self, bg=t.PANEL)
        self._top.pack(fill="x", padx=8, pady=(8, 3))
        header = tk.Frame(self._top, bg=t.PANEL)
        header.pack(side="left", fill="x", expand=True, padx=13, pady=7)
        brand = self.text(header, "✦  LaLa  ｜  飄流幻境 RE", size=17, bold=True,
                          color=t.SECTION)
        brand.pack(anchor="w")
        subtitle = self.text(header, "等待登入與角色資料同步  •  正式伺服器尚未接入",
                             size=10, color=t.MUTED)
        subtitle.pack(anchor="w", pady=(3, 0))
        self._chrome.bind_drag(self._top, header, brand, subtitle)
        actions = tk.Frame(self._top, bg=t.PANEL)
        actions.pack(side="right", padx=12, pady=8)
        self.text(actions, "● 離線預覽", color=t.WARN, size=10).pack(side="left", padx=11)
        self._button(actions, "登入／選角", lambda: self.open_feature("accounts")).pack(side="left", padx=3)
        self._button(actions, "中斷連線", lambda: self._offline_notice(), width=10).pack(side="left", padx=3)
        # 系統白色標題列移除後，保留最小化與關閉的操作入口（不提供最大化）。
        self._minimize_button = self._button(actions, "─", self._chrome.minimize, width=3)
        self._minimize_button.pack(side="left", padx=(12, 3))
        self._close_button = self._button(actions, "✕", self.destroy, width=3)
        self._close_button.pack(side="left", padx=3)

        body = tk.Frame(self, bg=t.BG)
        body.pack(fill="both", expand=True, padx=9, pady=(3, 8))
        body.columnconfigure(0, weight=1, minsize=0)
        body.columnconfigure(1, weight=0, minsize=t.MAP_SIZE[0])
        body.rowconfigure(0, weight=1)
        left = self._panel(body, bg=t.PANEL, border=False)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right = self._panel(body, bg=t.PANEL, border=False)
        right.grid(row=0, column=1, sticky="nsew")
        right.configure(width=t.MAP_SIZE[0])
        right.grid_propagate(False)
        self._build_left(left)
        self._build_right(right)

    def _offline_notice(self):
        self._append_event("目前沒有建立連線，沒有任何中斷動作。")

    def _build_left(self, parent):
        navbar = self._panel(parent, bg=t.SURFACE)
        navbar.pack(fill="x", pady=(0, 6))
        for key in t.QUICK_KEYS:
            feature = BY_KEY[key]
            # 舊版為 34px 原版遊戲 PNG；P0 不複製官方貼圖，以圓形底板佔位。
            plate = tk.Frame(navbar, bg=t.SURFACE)
            plate.pack(side="left", expand=True, fill="x", padx=2, pady=5)
            canvas = tk.Canvas(plate, width=44, height=41, bg=t.SURFACE, bd=0,
                               highlightthickness=0, cursor="hand2")
            canvas.pack(anchor="center")
            canvas.create_oval(4, 2, 40, 38, fill="#2d5165", outline=t.SECTION, width=1.5)
            caption = feature.title.replace("管理", "").replace("控制", "").replace("出戰", "")
            symbol = caption[:2]
            canvas.create_text(22, 20, text=symbol, fill=t.TEXT, font=(self._font, 10, "bold"))
            canvas.bind("<Button-1>", lambda _event, k=key: self.open_feature(k))
            name = self.text(plate, feature.title, size=8, color=t.MUTED, cursor="hand2")
            name.pack()
            name.bind("<Button-1>", lambda _event, k=key: self.open_feature(k))

        tabs = tk.Frame(parent, bg=t.PANEL)
        tabs.pack(fill="x", padx=6, pady=(2, 6))
        self.text(tabs, "主頁  /  角色概況", size=12, color=t.SECTION, bold=True).pack(side="left", padx=6)
        self._button(tabs, "全部功能（27）", self._show_all_features).pack(side="right")
        self._button(tabs, "經驗效率", lambda: self.open_feature("efficiency")).pack(side="right", padx=6)

        content = tk.Frame(parent, bg=t.PANEL)
        content.pack(fill="both", expand=True, padx=4)
        self._build_overview(content)
        self._build_chat(parent)

    def _build_overview(self, parent):
        for i in range(4):
            parent.rowconfigure(i, weight=1, uniform="overview", minsize=55)
        parent.columnconfigure(0, weight=1)
        for row_index, row in enumerate(t.OVERVIEW_ROWS):
            line = tk.Frame(parent, bg=t.PANEL)
            line.grid(row=row_index, column=0, sticky="nsew")
            for col_index, (title, feature_key) in enumerate(row):
                line.columnconfigure(col_index, weight=1, uniform=f"card{row_index}")
                card = self._panel(line, bg=t.SURFACE)
                card.grid(row=0, column=col_index, sticky="nsew", padx=3, pady=3)
                header = tk.Frame(card, bg=t.SURFACE)
                header.pack(fill="x", padx=8, pady=(7, 0))
                self.text(header, title, size=11, bold=True, color=t.SECTION).pack(side="left")
                self._button(header, "開啟", lambda k=feature_key: self.open_feature(k),
                             width=4).pack(side="right")
                detail = {
                    "characters": "角色：等待登入\n夥伴：等待同步",
                    "tent": "離線｜所有自動操作已停用",
                    "battle_ai": "自動戰鬥：未啟用",
                    "world": "自動徘徊：未啟用",
                    "expeditions": "遠征資料：尚未同步",
                    "supplies": "沒有可信的補給紀錄",
                    "alchemy": "煉金：尚未執行",
                    "crafting": "製作：尚未執行",
                    "party": "隊伍：等待角色同步",
                    "efficiency": "經驗資料：等待首場紀錄",
                }[feature_key]
                self.text(card, detail, size=10, color=t.MUTED, anchor="nw",
                          justify="left").pack(fill="both", expand=True, padx=10, pady=(6, 6))

    def _build_chat(self, parent):
        area = self._panel(parent, bg=t.SURFACE)
        area.pack(side="bottom", fill="x", padx=4, pady=(6, 1))
        title = tk.Frame(area, bg=t.SURFACE)
        title.pack(fill="x", padx=9, pady=5)
        self.text(title, "聊天", size=11, bold=True, color=t.SECTION).pack(side="left")
        self.text(title, "尚未連線／不可傳送", size=9, color=t.WARN).pack(side="right")
        chat = tk.Text(area, height=3, bg=t.PANEL, fg=t.MUTED, wrap="word",
                       relief="flat", font=(self._font, 10), borderwidth=0)
        chat.insert("end", "聊天紀錄需登入並取得伺服器資料後才會顯示。\n")
        chat.configure(state="disabled")
        chat.pack(fill="x", padx=9, pady=(0, 8))

    def _build_right(self, parent):
        title = tk.Frame(parent, bg=t.PANEL)
        title.pack(fill="x", pady=(1, 5))
        self.text(title, "小地圖  /  場景座標", size=11, bold=True,
                  color=t.SECTION).pack(side="left", padx=8)
        self._button(title, "地圖／導航", lambda: self.open_feature("world")).pack(
            side="right", padx=5)
        self._map_canvas = tk.Canvas(parent, width=t.MAP_SIZE[0] - 10,
                                    height=t.MAP_SIZE[1], bg=t.SURFACE,
                                    relief="flat", highlightbackground=t.BORDER,
                                    highlightthickness=1)
        self._map_canvas.pack(fill="x", padx=4)
        self._map_canvas.bind("<Configure>", self._paint_map)

        tabs = ttk.Notebook(parent, style="Classic.TNotebook")
        tabs.pack(fill="both", expand=True, pady=(8, 0), padx=4)
        events = self._panel(tabs, bg=t.PANEL, border=False)
        battle = self._panel(tabs, bg=t.PANEL, border=False)
        tabs.add(events, text="事件紀錄")
        tabs.add(battle, text="戰場陣形")
        self._events = tk.Text(events, bg=t.PANEL, fg=t.MUTED, relief="flat",
                               font=(self._font, 10), height=8, wrap="word",
                               insertbackground=t.TEXT, state="normal")
        self._events.insert("end", "[系統] LaLa 經典介面離線預覽\n[安全] 沒有讀取任何真實角色或遊戲封包\n")
        self._events.configure(state="disabled")
        self._events.pack(fill="both", expand=True, padx=6, pady=6)
        self.text(battle, "戰場尚未同步", size=12, color=t.WARN).pack(pady=(40, 8))
        self.text(battle, "戰場陣形將沿用舊版格位概念；\n此 P0 不顯示假敵人、假血量或假座標。",
                  size=10, color=t.MUTED, justify="center").pack()

    def _paint_map(self, _event=None):
        c = self._map_canvas
        w, h = max(c.winfo_width(), 2), max(c.winfo_height(), 2)
        c.delete("all")
        for x in range(16, w, 24):
            c.create_line(x, 0, x, h, fill="#1d4054")
        for y in range(15, h, 24):
            c.create_line(0, y, w, y, fill="#1d4054")
        c.create_rectangle(16, 18, w-16, h-17, outline=t.BORDER)
        c.create_text(w/2, h/2-14, text="尚無小地圖資料", fill=t.SECTION,
                      font=(self._font, 15, "bold"))
        c.create_text(w/2, h/2+17, text="場景與 NPC 資料待官方資源驗證",
                      fill=t.MUTED, font=(self._font, 9))

    def _append_event(self, message):
        self._events.configure(state="normal")
        self._events.insert("end", f"[預覽] {message}\n")
        self._events.see("end")
        self._events.configure(state="disabled")

    def _show_all_features(self):
        window = self._feature_windows.get("_catalog")
        if window is not None and window.winfo_exists():
            window.deiconify()
            window.lift()
            window.focus_set()
            return
        window = tk.Toplevel(self)
        self._feature_windows["_catalog"] = window
        window.title("LaLa ｜全部功能")
        apply_fixed_window(window, kind="dialog", parent=self)
        chrome = install_borderless(window)
        window.configure(bg=t.BG)
        search = tk.StringVar()
        toolbar = tk.Frame(window, bg=t.BG)
        toolbar.pack(fill="x", padx=20, pady=(10, 6))
        label = self.text(toolbar, "全部功能", size=17, bold=True, color=t.SECTION)
        label.pack(side="left")
        self._button(toolbar, "✕", window.destroy, width=3).pack(side="right")
        chrome.bind_drag(window, toolbar, label)
        entry = tk.Entry(window, textvariable=search, bg=t.FIELD, fg=t.TEXT,
                         insertbackground=t.TEXT, relief="flat",
                         font=(self._font, 12), highlightthickness=1,
                         highlightbackground=t.BORDER, highlightcolor=t.CYAN)
        entry.pack(fill="x", padx=20, ipady=7)
        listbox = tk.Listbox(window, bg=t.PANEL, fg=t.TEXT,
                             selectbackground=t.SURFACE_ACTIVE, selectforeground=t.CYAN,
                             activestyle="none", borderwidth=0, font=(self._font, 11),
                             relief="flat", exportselection=False)
        listbox.pack(fill="both", expand=True, padx=20, pady=(10, 17))
        visible = []

        def refresh(*_):
            visible[:] = [f for f in FEATURES if search.get().strip().casefold() in
                          (f.group + " " + f.title).casefold()]
            listbox.delete(0, "end")
            for f in visible:
                listbox.insert("end", f"   {f.group}  /  {f.title}")
        def selected(_event):
            indices = listbox.curselection()
            if indices:
                self.open_feature(visible[indices[0]].key)
        listbox.bind("<Double-Button-1>", selected)
        listbox.bind("<Return>", selected)
        search.trace_add("write", refresh)
        refresh()

    def open_feature(self, key):
        if key not in BY_KEY:
            return
        window = self._feature_windows.get(key)
        if window is not None and window.winfo_exists():
            window.deiconify()
            window.lift()
            window.focus_set()
            return
        feature = BY_KEY[key]
        window = tk.Toplevel(self)
        self._feature_windows[key] = window
        window.title(f"LaLa ｜{feature.title}（UI 預覽）")
        apply_fixed_window(window, kind="dialog", parent=self)
        chrome = install_borderless(window)
        window.configure(bg=t.BG)
        pane = self._panel(window, bg=t.PANEL)
        pane.pack(fill="both", expand=True, padx=15, pady=15)
        toolbar = tk.Frame(pane, bg=t.PANEL)
        toolbar.pack(fill="x", padx=24, pady=(11, 6))
        label = self.text(toolbar, feature.title, size=21, bold=True, color=t.SECTION)
        label.pack(side="left")
        self._button(toolbar, "✕", window.destroy, width=3).pack(side="right")
        chrome.bind_drag(window, pane, toolbar, label)
        self.text(pane, feature.description, size=12, wraplength=510,
                  justify="left").pack(anchor="w", padx=24)
        self.text(pane, "目前僅有 UI 佔位，尚未接入遊戲功能。",
                  size=12, color=t.WARN).pack(anchor="w", padx=24, pady=(20, 8))
        self.text(pane, "舊版參考：" + feature.legacy_area, size=10,
                  color=t.MUTED, wraplength=510, justify="left").pack(anchor="w", padx=24)
        self._button(pane, "關閉", window.destroy).pack(anchor="e", side="bottom", padx=24, pady=20)


def main():
    try:
        LaLaDesktop().mainloop()
    except tk.TclError as exc:
        raise SystemExit(f"無法啟動 LaLa 桌面 UI：{exc}") from exc
