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

rem Pillow 11.3.0 supports prebuilt Windows wheels for compatible CPython versions.
rem Prefer Python on PATH: "py -3" can select unsupported Python 3.15 on CI.
where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>&1
    if not errorlevel 1 set "BASE_PY=python"
)
if defined BASE_PY goto :create_venv

where py >nul 2>&1
if not errorlevel 1 (
    py -3.11 -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>&1
    if not errorlevel 1 set "BASE_PY=py -3.11"
    py -3.12 -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>&1
    if not errorlevel 1 if not defined BASE_PY set "BASE_PY=py -3.12"
    py -3.13 -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>&1
    if not errorlevel 1 if not defined BASE_PY set "BASE_PY=py -3.13"
    py -3.10 -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>&1
    if not errorlevel 1 if not defined BASE_PY set "BASE_PY=py -3.10"
)
if not defined BASE_PY goto :python_error

:create_venv

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
"%VENV_PY%" -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>&1
if errorlevel 1 goto :venv_error
if not exist "requirements-desktop.txt" goto :requirements_error

rem Only download on first run or if the exact pinned Pillow dependency is missing.
"%VENV_PY%" -c "import PIL; from PIL import Image, ImageTk; import tkinter; assert PIL.__version__ == '11.3.0'" >nul 2>&1
if errorlevel 1 (
    echo [LaLa] Installing desktop image dependency. Internet may be required.
    "%VENV_PY%" -m pip --disable-pip-version-check install --only-binary=:all: -r "requirements-desktop.txt"
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
echo [LaLa] ERROR: Python 3.10 - 3.13 is required for Pillow 11.3.0.
echo [LaLa] Install Python 3.11 from https://www.python.org/downloads/
echo [LaLa] Run this BAT again after installation.
goto :failed

:venv_error
echo [LaLa] ERROR: Cannot create or use .venv\Scripts\python.exe.
echo [LaLa] Check Python installation, folder permissions, and disk space.
echo [LaLa] If .venv uses an unsupported Python, rename it and retry.
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
