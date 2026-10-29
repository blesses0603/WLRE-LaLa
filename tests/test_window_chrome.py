"""不需要顯示環境的邏輯測試：拖曳限界及綁定行為。"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from lala_desktop.window_chrome import BorderlessChrome


class BorderlessChromeLogicTests(unittest.TestCase):
    def test_drag_is_clamped_and_does_not_change_16_9_size(self):
        window = Mock()
        window.winfo_x.return_value = 200
        window.winfo_y.return_value = 100
        window.winfo_width.return_value = 800
        window.winfo_height.return_value = 450
        window.winfo_screenwidth.return_value = 1920
        window.winfo_screenheight.return_value = 1080
        controller = object.__new__(BorderlessChrome)
        controller.window = window
        controller._drag_origin = None
        controller.start_drag(SimpleNamespace(x_root=500, y_root=300))
        controller.drag(SimpleNamespace(x_root=3000, y_root=2800))
        window.geometry.assert_called_with("+1120+630")
        controller.stop_drag()
        controller.drag(SimpleNamespace(x_root=600, y_root=400))
        self.assertEqual(window.geometry.call_count, 1)

    def test_only_explicit_drag_targets_receive_binding(self):
        window = Mock()
        window.bind.return_value = ""
        window.after_idle = Mock()
        controller = BorderlessChrome(window)
        window.overrideredirect.assert_called_once_with(True)
        title = Mock()
        controller.bind_drag(title)
        self.assertEqual(title.bind.call_count, 3)
        self.assertTrue(any(call.args[0] == "<B1-Motion>" for call in title.bind.call_args_list))

    def test_minimize_relaxes_override_then_iconifies(self):
        window = Mock()
        controller = object.__new__(BorderlessChrome)
        controller.window = window
        controller._drag_origin = (1, 2, 3, 4)
        controller._awaiting_restore = False
        controller.minimize()
        self.assertEqual(window.method_calls[-3:],
                         [unittest.mock.call.overrideredirect(False),
                          unittest.mock.call.update_idletasks(),
                          unittest.mock.call.iconify()])
        self.assertTrue(controller._awaiting_restore)
