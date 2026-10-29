@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem LaLa Desktop one-click launcher (Windows).
rem Double-click normally; use --check for CI dependency smoke tests.

cd /d "%~dp0"
if errorlevel 1 goto :path_error

set "CHECK_ONLY=0"
if /I "%~1"=="--check" set "CHECK_ONLY=1"
set "VENV_DIR=%CD%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "BASE_PY="

if exist "%VENV_PY%" goto :environment_ready

rem Python 3.10+ is required. Prefer the Windows Python launcher when possible.
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 set "BASE_PY=py -3"
)
if defined BASE_PY goto :create_venv

where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 set "BASE_PY=python"
)
if not defined BASE_PY goto :python_error

:create_venv
echo [LaLa] Creating local Python environment...
%BASE_PY% -m venv "%VENV_DIR%"
if errorlevel 1 goto :venv_error

:environment_ready
if not exist "%VENV_PY%" goto :venv_error
"%VENV_PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto :venv_error
if not exist "requirements-desktop.txt" goto :requirements_error

rem Only download on first run or if the exact pinned Pillow dependency is missing.
"%VENV_PY%" -c "import PIL; from PIL import Image, ImageTk; import tkinter; assert PIL.__version__ == '11.3.0'" >nul 2>&1
if errorlevel 1 (
    echo [LaLa] Installing desktop image dependency (internet may be required)...
    "%VENV_PY%" -m pip --disable-pip-version-check install -r "requirements-desktop.txt"
    if errorlevel 1 goto :install_error
)

"%VENV_PY%" -c "import PIL; from PIL import Image, ImageTk; import tkinter; assert PIL.__version__ == '11.3.0'" >nul 2>&1
if errorlevel 1 goto :install_error

if "%CHECK_ONLY%"=="1" (
    echo [LaLa] Python and desktop dependencies are ready.
    exit /b 0
)

echo [LaLa] Starting LaLa desktop UI...
"%VENV_PY%" -m lala_desktop
if errorlevel 1 goto :launch_error
exit /b 0

:path_error
echo [LaLa] ERROR: Cannot open the folder containing run_lala.bat.
goto :failed

:python_error
echo [LaLa] ERROR: Python 3.10 or later is required.
echo [LaLa] Install Python from https://www.python.org/downloads/
echo [LaLa] Run this BAT again after installation.
goto :failed

:venv_error
echo [LaLa] ERROR: Cannot create or use .venv\Scripts\python.exe.
echo [LaLa] Check Python installation, folder permissions, and disk space.
goto :failed

:requirements_error
echo [LaLa] ERROR: requirements-desktop.txt was not found.
echo [LaLa] Extract the entire project ZIP before launching.
goto :failed

:install_error
echo [LaLa] ERROR: Unable to install Pillow.
echo [LaLa] Check your internet connection or Python environment.
goto :failed

:launch_error
echo [LaLa] ERROR: The application could not start. Read the error above.
goto :failed

:failed
if "%CHECK_ONLY%"=="0" pause
exit /b 1
