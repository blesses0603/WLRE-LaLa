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

    def test_launcher_explains_missing_python(self):
        self.assertIn("py -0p", self.content)
        self.assertIn("Python 3.10 is not supported by Pillow 13.", self.content)
        self.assertIn("py -3 --version", self.content)
        self.assertIn("where py", self.content)
        self.assertIn('if "%CHECK_ONLY%"=="0" pause', self.content)
        self.assertIn("exit /b 1", self.content)
