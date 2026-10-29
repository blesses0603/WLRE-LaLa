"""靜態檢查 BAT；Windows CI 驗證 cmd.exe、依賴和版本偵測。"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LauncherContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = (ROOT / "run_lala.bat").read_text(encoding="utf-8")

    def test_launcher_runs_local_environment(self):
        self.assertIn('set "VENV_DIR=%CD%\\.venv"', self.content)
        self.assertIn('"%VENV_PY%" -m lala_desktop', self.content)
        self.assertIn('-m venv "%VENV_DIR%"', self.content)

    def test_compatible_python_autodetection(self):
        self.assertIn("where py >nul 2>&1", self.content)
        self.assertIn("call :find_compatible_python", self.content)
        self.assertIn('py -3 -c "import sys', self.content)
        for version in ("3.11", "3.12", "3.13", "3.14", "3.15"):
            self.assertIn(f"call :try_py_version {version}", self.content)
        self.assertIn('set "BASE_EXE=py"', self.content)
        self.assertIn('set "BASE_ARG=-3"', self.content)
        self.assertIn('set "BASE_ARG=-%~1"', self.content)
        self.assertIn("where python >nul 2>&1", self.content)
        self.assertIn("where python3 >nul 2>&1", self.content)
        self.assertIn('if "%PY_ONLY%"=="1" exit /b 0', self.content)
        self.assertIn("(3, 11) <= sys.version_info[:2] <= (3, 15)", self.content)
        self.assertNotIn("call :try_py_version 3.10", self.content)

    def test_unique_labels_and_no_system_python_modification(self):
        labels = re.findall(r"^:([A-Za-z0-9_]+)$", self.content, flags=re.M)
        self.assertEqual(len(labels), len(set(labels)))
        self.assertIn('"%VENV_PY%" -m pip', self.content)
        self.assertNotIn("rmdir ", self.content.lower())
        self.assertNotIn("del /", self.content.lower())

    def test_version_matched_pillow_install(self):
        self.assertIn('--only-binary=:all: -r "requirements-desktop.txt"', self.content)
        self.assertIn("assert PIL.__version__ == '13.0.0'", self.content)
        self.assertNotIn("12.0.0", self.content)
        requirements = (ROOT / "requirements-desktop.txt").read_bytes().decode("ascii")
        self.assertIn("Pillow==13.0.0", requirements)
        self.assertNotIn("Pillow==12", requirements)
        self.assertIn("import tkinter", self.content)

    def test_ci_check_does_not_open_gui(self):
        self.assertIn('if /I "%~1"=="--check"', self.content)
        self.assertIn('if /I "%~2"=="--py-only"', self.content)
        self.assertLess(self.content.index('if "%CHECK_ONLY%"=="1"'),
                        self.content.index('"%VENV_PY%" -m lala_desktop'))

    def test_boot_preflight_before_gui_and_skip_during_ci_check(self):
        # A single combined call must run after Pillow verification, before the GUI.
        call = ('"%VENV_PY%" -m lala_core.resource_inspector '
                '--online --manifests --json --timeout 3')
        self.assertIn(call, self.content)
        self.assertLess(self.content.index('if "%CHECK_ONLY%"=="1" ('),
                        self.content.index(call))
        self.assertLess(self.content.index(call),
                        self.content.index('"%VENV_PY%" -m lala_desktop'))
        self.assertIn('set "LALA_STARTUP_RESOURCE_STATUS=failed"', self.content)
        self.assertIn('set "LALA_STARTUP_RESOURCE_STATUS=transport_checked"', self.content)
        self.assertIn("Launching OFFLINE UI only.", self.content)
        self.assertIn('CI: --check skips network and GUI.', self.content)
        self.assertIn('Diagnostic: --diagnose keeps network result visible.', self.content)

    def test_explicit_diagnostic_mode_keeps_error_visible_without_gui(self):
        self.assertIn('if /I "%~1"=="--diagnose" set "DIAGNOSE_ONLY=1"', self.content)
        self.assertIn("Diagnostic mode: no GUI opened.", self.content)
        self.assertIn("Diagnostic mode complete.", self.content)
        self.assertLess(self.content.index('if "%DIAGNOSE_ONLY%"=="1" ('),
                        self.content.index('"%VENV_PY%" -m lala_desktop'))

    def test_single_server_tcp_probe_uses_explicit_opt_in(self):
        self.assertIn('if /I "%~1"=="--probe-server" set "PROBE_ONLY=1"', self.content)
        probe = '"%VENV_PY%" -m lala_core.server_probe --online --line 101 --timeout 3 --json'
        self.assertIn(probe, self.content)
        self.assertLess(self.content.index('if "%CHECK_ONLY%"=="1" ('),
                        self.content.index(probe))
        self.assertLess(self.content.index(probe),
                        self.content.index('"%VENV_PY%" -m lala_desktop.launcher'))
        self.assertIn("no login packets.", self.content)

    def test_gui_launches_without_covering_console(self):
        self.assertIn('if exist "%VENV_DIR%\\Scripts\\pythonw.exe" (', self.content)
        self.assertIn('"%VENV_PY%" -m lala_desktop.launcher', self.content)
        self.assertNotIn('start "" "%VENV_DIR%\\Scripts\\pythonw.exe"', self.content)
        self.assertLess(self.content.index("LALA_STARTUP_RESOURCE_STATUS=failed"),
                        self.content.index("pythonw.exe"))
        self.assertIn('"%VENV_PY%" -m lala_desktop', self.content)

    def test_launcher_uses_fresh_process_result_after_failed_resource_check(self):
        self.assertIn('"%VENV_PY%" -m lala_desktop.launcher', self.content)
        self.assertLess(self.content.index("LALA_STARTUP_RESOURCE_STATUS=failed"),
                        self.content.index('"%VENV_PY%" -m lala_desktop.launcher'))
        self.assertIn("if errorlevel 1 goto :launch_error", self.content)

    def test_gui_launcher_exposes_windows_pythonw_errors(self):
        code = (ROOT / "lala_desktop" / "__main__.py").read_text(encoding="utf-8")
        self.assertIn('MessageBoxW(', code)
        self.assertIn('python.exe -m lala_desktop', code)

    def test_launcher_explains_missing_python(self):
        self.assertIn("py -0p", self.content)
        self.assertIn("Python 3.10 is not supported by Pillow 13.", self.content)
        self.assertIn("py -3 --version", self.content)
        self.assertIn("where py", self.content)
        self.assertIn('if "%CHECK_ONLY%"=="0" pause', self.content)
        self.assertIn("exit /b 1", self.content)
