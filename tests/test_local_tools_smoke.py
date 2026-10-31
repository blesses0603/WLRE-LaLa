"""Xvfb 介面互動：輸入實際離線資料，確認呼叫共用計算服務。"""
import os
import unittest


@unittest.skipUnless(os.name == "nt" or os.environ.get("DISPLAY"),
                     "需要 Windows 桌面或 xvfb-run")
class LocalPlanningUISmokeTests(unittest.TestCase):
    def test_local_planning_tools_actually_calculate(self):
        import tkinter as tk
        from lala_desktop.app import LaLaDesktop

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        root = LaLaDesktop()
        try:
            cases = {
                "efficiency": (["100", "500", "3600", "900"], "400.0 EXP"),
                "crafting": (["7", "2", "12:3,13:1", "12:7,13:2", "12:1"],
                             "材料條件符合"),
                "expeditions": (["1:70:1,2:90:1", "1,2", "2", "60"],
                                "本機條件通過"),
            }
            for key, (values, expected) in cases.items():
                root.open_feature(key)
                root.update()
                window = root._feature_windows[key]
                widgets = list(descendants(window))
                entries = [w for w in widgets if isinstance(w, tk.Entry)]
                self.assertEqual(len(entries), len(values), key)
                for w, value in zip(entries, values):
                    w.delete(0, "end")
                    w.insert(0, value)
                buttons = [w for w in widgets if getattr(w, "label", "") == "本機計算"]
                self.assertEqual(len(buttons), 1, key)
                buttons[0].invoke()
                root.update()
                messages = []
                for widget in widgets:
                    if isinstance(widget, tk.Label):
                        variable = widget.cget("textvariable")
                        if variable:
                            messages.append(str(root.getvar(variable)))
                self.assertTrue(any(expected in msg for msg in messages),
                                (key, messages))
        finally:
            root.destroy()
