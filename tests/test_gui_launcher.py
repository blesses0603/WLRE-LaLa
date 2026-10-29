"""Windows launcher process contract: use a *fresh* Popen result, not stale ERRORLEVEL."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from lala_desktop import launcher


class GuiLauncherTests(unittest.TestCase):
    def test_spawns_pythonw_and_inherits_current_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            scripts = Path(temp)
            exe = scripts / "python.exe"
            (scripts / "pythonw.exe").touch()
            spawn = Mock()
            with patch.dict(os.environ, {"LALA_STARTUP_RESOURCE_STATUS": "failed"}):
                self.assertEqual(launcher.launch_gui(exe, popen=spawn), 0)
                self.assertEqual(os.environ["LALA_STARTUP_RESOURCE_STATUS"], "failed")
            spawn.assert_called_once()
            args, kwargs = spawn.call_args
            self.assertEqual(args[0], [str(scripts / "pythonw.exe"), "-m", "lala_desktop"])
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
            self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
            self.assertTrue(kwargs["close_fds"])
            self.assertNotIn("env", kwargs)

    def test_missing_pythonw_fails_without_gui(self):
        with tempfile.TemporaryDirectory() as temp:
            spawn = Mock()
            with self.assertRaises(FileNotFoundError):
                launcher.launch_gui(Path(temp) / "python.exe", popen=spawn)
            spawn.assert_not_called()

    def test_process_creation_error_returns_nonzero_without_false_success(self):
        with patch.object(launcher, "launch_gui", side_effect=OSError("mock launch error")):
            self.assertEqual(launcher.main(), 1)

    def test_successful_launch_returns_zero_even_after_resource_failure(self):
        with patch.object(launcher, "launch_gui", return_value=0), patch.dict(
                os.environ, {"LALA_STARTUP_RESOURCE_STATUS": "failed"}):
            self.assertEqual(launcher.main(), 0)
