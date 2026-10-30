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

    def test_experimental_login_requires_one_click_consent_and_consumes_it(self):
        from lala_desktop.app import LaLaDesktop
        from lala_desktop import login_tools
        from lala_core.legacy_login_trial import LegacyTrialResult
        from unittest.mock import Mock
        import time

        fake = Mock()
        fake.authenticate.return_value = LegacyTrialResult(True, True, (1,))
        with patch.object(login_tools, "verify_installed",
                          return_value={"resources_installed": True}), \
             patch.object(login_tools, "LegacyLoginTrial", return_value=fake):
            root = LaLaDesktop()
            try:
                root.open_feature("accounts")
                root.update()
                window = root._feature_windows["accounts"]
                def descendants(widget):
                    for child in widget.winfo_children():
                        yield child
                        yield from descendants(child)
                all_widgets = list(descendants(window))
                fields = [w for w in all_widgets if type(w) is tk.Entry]
                checkbox = next(w for w in all_widgets if type(w) is tk.Checkbutton)
                login = next(w for w in all_widgets if getattr(w, "label", "") == "登入")
                fields[0].insert(0, "fake-account")
                fields[1].insert(0, "fake-password")
                self.assertEqual(checkbox.var if hasattr(checkbox, "var") else
                                 root.getvar(checkbox.cget("variable")), 0)
                # Default UI still has no path that sends credentials.
                login.invoke()
                root.update()
                fake.authenticate.assert_not_called()
                fields[1].insert(0, "fake-password")
                checkbox.invoke()  # real user gesture
                login.invoke()
                for _ in range(10):
                    root.update()
                    if fake.authenticate.called:
                        break
                    time.sleep(.015)
                fake.authenticate.assert_called_once()
                self.assertEqual(root.getvar(checkbox.cget("variable")), 0)
                self.assertEqual(fields[1].get(), "")
                self.assertFalse(window._lala_login_coordinator.session.view().connected)
            finally:
                root.destroy()

    def test_strict_role_snapshot_is_shown_but_not_marked_online(self):
        from lala_desktop.app import LaLaDesktop
        from lala_desktop import login_tools
        from lala_core.legacy_login_trial import LegacyTrialResult, LegacyRoleTrialResult
        from unittest.mock import Mock
        import time

        fake = Mock()
        fake.authenticate.return_value = LegacyTrialResult(True, True, (1,))
        fake.select_role.return_value = LegacyRoleTrialResult(
            1, True, False, True, 6789, "測試玩家", 110, 25, 47)
        with patch.object(login_tools, "verify_installed",
                          return_value={"resources_installed": True}), \
             patch.object(login_tools, "LegacyLoginTrial", return_value=fake):
            root = LaLaDesktop()
            try:
                root.open_feature("accounts")
                root.update()
                dialog = root._feature_windows["accounts"]
                def descendants(widget):
                    for child in widget.winfo_children():
                        yield child
                        yield from descendants(child)
                widgets = list(descendants(dialog))
                fields = [w for w in widgets if type(w) is tk.Entry]
                checkbox = next(w for w in widgets if type(w) is tk.Checkbutton)
                buttons = {w.label: w for w in widgets if getattr(w, "label", "")}
                fields[0].insert(0, "fake")
                fields[1].insert(0, "fake")
                checkbox.invoke()
                buttons["登入"].invoke()
                for _ in range(40):
                    root.update()
                    if "readonly" in [str(w.cget("state")) for w in widgets
                                      if w.winfo_class() == "TCombobox"]:
                        break
                    time.sleep(.015)
                # Ensure login worker GUI message was consumed before selecting.
                for _ in range(40):
                    root.update()
                    if any(str(root.getvar(w.cget("textvariable"))).find("等待選角") >= 0
                           for w in widgets if isinstance(w, tk.Label)
                           and w.cget("textvariable")):
                        break
                    time.sleep(.015)
                buttons["選擇角色"].invoke()
                for _ in range(60):
                    root.update()
                    if fake.select_role.called and any(
                        "S3-1 角色資料完整解析" in
                        str(root.getvar(w.cget("textvariable")))
                        for w in widgets if isinstance(w, tk.Label)
                        and w.cget("textvariable")
                    ):
                        break
                    time.sleep(.015)
                fake.select_role.assert_called_once_with(1)
                labels = [str(root.getvar(w.cget("textvariable")))
                          for w in widgets if isinstance(w, tk.Label)
                          and w.cget("textvariable")]
                self.assertTrue(any("6789" in label and "110" in label
                                    and "25, 47" in label for label in labels), labels)
                self.assertTrue(any("S3-1 角色資料完整解析" in label
                                    for label in labels), labels)
                self.assertFalse(dialog._lala_login_coordinator.session.view().connected)
                buttons["中斷"].invoke()
                labels = [str(root.getvar(w.cget("textvariable")))
                          for w in widgets if isinstance(w, tk.Label)
                          and w.cget("textvariable")]
                self.assertFalse(any("測試玩家" in label for label in labels))
            finally:
                root.destroy()

    def test_failed_role_trial_clears_stale_role_selection(self):
        from lala_desktop.app import LaLaDesktop
        from lala_desktop import login_tools
        from lala_core.login import LoginError
        from lala_core.legacy_login_trial import LegacyTrialResult
        from unittest.mock import Mock
        import time

        fake = Mock()
        fake.authenticate.return_value = LegacyTrialResult(True, True, (1,))
        fake.select_role.side_effect = LoginError("模擬角色回覆中止")
        with patch.object(login_tools, "verify_installed",
                          return_value={"resources_installed": True}), \
             patch.object(login_tools, "LegacyLoginTrial", return_value=fake):
            root = LaLaDesktop()
            try:
                root.open_feature("accounts")
                root.update()
                dialog = root._feature_windows["accounts"]

                def descendants(widget):
                    for child in widget.winfo_children():
                        yield child
                        yield from descendants(child)

                widgets = list(descendants(dialog))
                fields = [w for w in widgets if type(w) is tk.Entry]
                checkbox = next(w for w in widgets if type(w) is tk.Checkbutton)
                buttons = {w.label: w for w in widgets if getattr(w, "label", "")}
                role_box = [w for w in widgets
                            if w.winfo_class() == "TCombobox"][1]
                fields[0].insert(0, "fake")
                fields[1].insert(0, "fake")
                checkbox.invoke()
                buttons["登入"].invoke()
                for _ in range(80):
                    root.update()
                    if str(role_box.cget("state")) == "readonly":
                        break
                    time.sleep(.015)
                self.assertEqual(str(role_box.cget("state")), "readonly")
                buttons["選擇角色"].invoke()
                for _ in range(80):
                    root.update()
                    if any("模擬角色回覆中止" in str(root.getvar(w.cget("textvariable")))
                           for w in widgets if isinstance(w, tk.Label)
                           and w.cget("textvariable")):
                        break
                    time.sleep(.015)
                fake.select_role.assert_called_once_with(1)
                self.assertEqual(str(role_box.cget("state")), "disabled")
                self.assertEqual(role_box.get(), "")
                self.assertFalse(dialog._lala_login_coordinator.session.view().connected)
                buttons["選擇角色"].invoke()
                fake.select_role.assert_called_once()
            finally:
                root.destroy()

    def test_manual_readonly_observation_is_opt_in_and_stays_untrusted(self):
        from lala_desktop.app import LaLaDesktop
        from lala_desktop import login_tools
        from lala_core.legacy_login_trial import (
            LegacyTrialResult, LegacyRoleTrialResult, LegacyReadOnlyObservation,
        )
        from unittest.mock import Mock
        import time

        fake = Mock()
        fake.authenticate.return_value = LegacyTrialResult(True, True, (1,))
        fake.select_role.return_value = LegacyRoleTrialResult(
            1, True, False, True, 6789, "測試玩家", 110, 25, 47,
            ongoing_connection=True, init_acks_sent=True)
        fake.observe_readonly.return_value = LegacyReadOnlyObservation(3, 1)
        with patch.object(login_tools, "verify_installed",
                          return_value={"resources_installed": True}), \
             patch.object(login_tools, "LegacyLoginTrial", return_value=fake):
            root = LaLaDesktop()
            try:
                root.open_feature("accounts")
                root.update()
                dialog = root._feature_windows["accounts"]

                def descendants(widget):
                    for child in widget.winfo_children():
                        yield child
                        yield from descendants(child)

                widgets = list(descendants(dialog))
                fields = [w for w in widgets if type(w) is tk.Entry]
                checkboxes = [w for w in widgets if type(w) is tk.Checkbutton]
                self.assertEqual(len(checkboxes), 2)
                self.assertIn("唯讀觀測 60 秒", checkboxes[1].cget("text"))
                self.assertEqual(root.getvar(checkboxes[1].cget("variable")), 0)
                buttons = {w.label: w for w in widgets if getattr(w, "label", "")}
                fields[0].insert(0, "fake")
                fields[1].insert(0, "fake")
                checkboxes[0].invoke()
                buttons["登入"].invoke()
                for _ in range(80):
                    root.update()
                    if any("等待選角" in str(root.getvar(w.cget("textvariable")))
                           for w in widgets if isinstance(w, tk.Label)
                           and w.cget("textvariable")):
                        break
                    time.sleep(.015)
                checkboxes[1].invoke()
                buttons["選擇角色"].invoke()
                for _ in range(80):
                    root.update()
                    if fake.observe_readonly.called:
                        break
                    time.sleep(.015)
                fake.select_role.assert_called_once_with(1, keep_open=True)
                fake.observe_readonly.assert_called_once_with(duration=60)
                self.assertEqual(root.getvar(checkboxes[1].cget("variable")), 0)
                self.assertFalse(dialog._lala_login_coordinator.session.view().connected)
                for _ in range(80):
                    root.update()
                    if any("唯讀觀測完成" in str(root.getvar(w.cget("textvariable")))
                           for w in widgets if isinstance(w, tk.Label)
                           and w.cget("textvariable")):
                        break
                    time.sleep(.015)
                texts = [str(root.getvar(w.cget("textvariable")))
                         for w in widgets if isinstance(w, tk.Label)
                         and w.cget("textvariable")]
                self.assertTrue(any("唯讀觀測完成" in msg for msg in texts))
            finally:
                root.destroy()

    def test_main_header_disconnect_uses_login_controller(self):
        from lala_desktop.app import LaLaDesktop
        root = LaLaDesktop()
        try:
            root.open_feature("accounts")
            root.update()
            dialog = root._feature_windows["accounts"]
            coordinator = dialog._lala_login_coordinator
            buttons = [w for w in root.winfo_children()]
            root._disconnect_account()
            self.assertEqual(coordinator.view().phase, "disconnected")
            self.assertFalse(coordinator.session.view().connected)
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
