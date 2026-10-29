"""LaLa Canvas 圓角面板與按鈕：純 Tkinter，不需要第三方主題套件。"""
from math import cos, pi, sin
import tkinter as tk
from . import theme as t


def rounded_points(x1, y1, x2, y2, radius, segments=8):
    """用直線逼近真正圓弧，避免 Tk smooth=True 產生過度彎曲。"""
    if x2 <= x1 or y2 <= y1:
        return (x1, y1, x2, y2)
    radius = max(0.0, min(float(radius), (x2-x1)/2, (y2-y1)/2))
    if not radius:
        return (x1, y1, x2, y1, x2, y2, x1, y2)
    corners = (
        (x2-radius, y1+radius, -pi/2, 0),
        (x2-radius, y2-radius, 0, pi/2),
        (x1+radius, y2-radius, pi/2, pi),
        (x1+radius, y1+radius, pi, 3*pi/2),
    )
    points = []
    steps = max(2, int(segments))
    for cx, cy, start, end in corners:
        for j in range(steps+1):
            a = start + (end-start)*j/steps
            points.extend((cx+radius*cos(a), cy+radius*sin(a)))
    return tuple(points)


class RoundedPanel(tk.Frame):
    """將外框畫在 Canvas，內縮的 .content 承接 Tk 元件，避免出現直角底色。"""
    def __init__(self, parent, *, fill=t.PANEL, radius=16, border=True, inset=6):
        parent_bg = parent.cget("bg")
        super().__init__(parent, bg=parent_bg, bd=0, highlightthickness=0)
        self.fill = fill
        self.radius = radius
        self.outline = t.BORDER if border else fill
        self.inset = max(1, int(inset))
        self.canvas = tk.Canvas(self, bg=parent_bg, bd=0, highlightthickness=0)
        self.canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.content = tk.Frame(self, bg=fill, bd=0, highlightthickness=0)
        self.content.pack(fill="both", expand=True, padx=self.inset, pady=self.inset)
        self.bind("<Configure>", self._paint, add="+")

    def _paint(self, _event=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 2 or h < 2:
            return
        self.canvas.delete("round")
        self.canvas.create_polygon(
            rounded_points(1, 1, w-1, h-1, self.radius),
            fill=self.fill, outline=self.outline, width=1, tags=("round",))


class RoundedButton(tk.Canvas):
    """滑入／按下狀態與 Return、Space 鍵操作皆保留的圓角 Canvas 按鈕。"""
    def __init__(self, parent, text, command, *, width=None, emphasis=False, height=32,
                 radius=11, danger=False):
        self.label = text
        self.command = command
        self.radius = radius
        self.emphasis = emphasis
        self.danger = danger
        self._hover = False
        self._pressed = False
        self._enabled = True
        px = max(34, int(width)*9+20 if width is not None
                 else len(text)*(14 if any(ord(c)>127 for c in text) else 9)+24)
        super().__init__(parent, width=px, height=height, bg=parent.cget("bg"),
                         bd=0, highlightthickness=0, takefocus=True, cursor="hand2")
        for seq, callback in (
            ("<Configure>", self._paint), ("<Enter>", self._enter),
            ("<Leave>", self._leave), ("<ButtonPress-1>", self._press),
            ("<ButtonRelease-1>", self._release), ("<Return>", self._activate),
            ("<space>", self._activate), ("<FocusIn>", self._paint),
            ("<FocusOut>", self._paint),
        ):
            self.bind(seq, callback, add="+")
        self._paint()

    def _paint(self, _event=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2 or h <= 2:
            w, h = int(self.cget("width")), int(self.cget("height"))
        if self.danger:
            fill = "#744154" if self._hover else "#5b3546"
        elif self._pressed:
            fill = t.SURFACE
        elif self._hover:
            fill = "#365770"
        else:
            fill = t.FIELD if self.emphasis else t.SURFACE_ACTIVE
        if not self._enabled:
            fill = t.PANEL
        outline = t.CYAN if self.focus_get() is self or self._hover else t.BORDER
        foreground = t.DISABLED if not self._enabled else t.SECTION if self._hover else t.TEXT
        self.delete("all")
        self.create_polygon(rounded_points(1, 1, w-1, h-1, self.radius),
                            fill=fill, outline=outline, width=1.1,
                            tags=("round-button",))
        self.create_text(w/2, h/2, text=self.label, fill=foreground,
                         font=("Microsoft JhengHei UI", 10, "bold"),
                         tags=("round-button-label",))

    def _enter(self, _event):
        self._hover = True
        self._paint()

    def _leave(self, _event):
        self._hover = False
        self._pressed = False
        self._paint()

    def _press(self, _event):
        if self._enabled:
            self.focus_set()
            self._pressed = True
            self._paint()

    def _release(self, event):
        pressed = self._pressed
        self._pressed = False
        self._paint()
        if pressed and self._enabled and 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self.invoke()

    def _activate(self, _event):
        self.invoke()
        return "break"

    def invoke(self):
        if self._enabled:
            return self.command()
        return None

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        self.configure(cursor="hand2" if enabled else "arrow")
        self._paint()
