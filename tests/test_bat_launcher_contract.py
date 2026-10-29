"""跨平台靜態驗證 BAT 啟動器；實際 cmd.exe 驗證在 Windows CI 執行。"""
from pathlib import Path
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

    def test_launcher_installs_explicit_requirements_when_missing(self):
        self.assertIn('install -r "requirements-desktop.txt"', self.content)
        self.assertIn("assert PIL.__version__ == '11.3.0'", self.content)
        self.assertIn("if errorlevel 1 goto :install_error", self.content)
        self.assertIn("--only-binary=:all:", self.content)

    def test_compatible_python_selection(self):
        self.assertIn("<= (3, 13)", self.content)
        self.assertIn('set "BASE_PY=python"', self.content)
        self.assertIn('set "BASE_PY=py -3.11"', self.content)

    def test_ci_check_does_not_launch_gui(self):
        self.assertIn('if /I "%~1"=="--check"', self.content)
        self.assertLess(self.content.index('if "%CHECK_ONLY%"=="1"'),
                        self.content.index('"%VENV_PY%" -m lala_desktop'))

    def test_launcher_returns_error_code_and_keeps_error_visible(self):
        self.assertIn(":failed", self.content)
        self.assertIn('if "%CHECK_ONLY%"=="0" pause', self.content)
        self.assertIn("exit /b 1", self.content)
