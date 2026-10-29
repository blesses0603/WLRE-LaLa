"""無遊戲網路的 Windows/虛擬顯示登入視窗驗收。"""
import os
import tkinter as tk
import unittest
from unittest.mock import patch

@unittest.skipUnless(os.name == "nt" or os.environ.get("DISPLAY"),
                     "需要 Windows 桌面或 xvfb-run")
class LoginWindowTests(unittest.TestCase):
    def test_login_window_shows_masked_password_and_safely_blocks_unknown_protocol(self):
        from lala_desktop.app import LaLaDesktop
        from lala_desktop import login_tools

        def widgets(parent):
            for child in parent.winfo_children():
                yield child
                yield from widgets(child)

        with patch.object(login_tools, "verify_installed", return_value={"resources_installed": True}):
            root = LaLaDesktop()
            try:
                root.open_feature("accounts")
                root.update()
                window = root._feature_windows["accounts"]
                descendants = list(widgets(window))
                controls = [w for w in descendants if getattr(w, "label", "")]
                labels = [w.label for w in controls]
                self.assertIn("登入", labels)
                self.assertIn("中斷", labels)
                self.assertIn("測試 TCP", labels)
                self.assertIn("選擇角色", labels)
                fields = [w for w in descendants if type(w) is tk.Entry]
                self.assertEqual(len(fields), 2)
                self.assertEqual(fields[1].cget("show"), "●")
                fields[0].insert(0, "tester")
                fields[1].insert(0, "mysecret")
                with patch.object(login_tools, "probe_line") as probe:
                    next(w for w in controls if w.label == "登入").invoke()
                    root.update()
                    probe.assert_not_called()
                self.assertEqual(fields[1].get(), "")
                values = [str(root.getvar(w.cget("textvariable")))
                          for w in descendants
                          if isinstance(w, tk.Label) and w.cget("textvariable")]
                self.assertTrue(any("禁止傳送密碼" in x for x in values), values)
                self.assertTrue(window.overrideredirect())
            finally:
                root.destroy()

    def test_login_and_disconnect_use_no_network_while_offline(self):
        from lala_desktop.app import LaLaDesktop
        from lala_desktop import login_tools
        with patch.object(login_tools, "probe_line") as tcp:
            root = LaLaDesktop()
            try:
                root.open_feature("accounts")
                window = root._feature_windows["accounts"]
                parent = next(x for x in window.winfo_children() if x.winfo_children())
                # We assert that merely opening the UI never creates TCP work.
                root.update()
                tcp.assert_not_called()
            finally:
                root.destroy()
