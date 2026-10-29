@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem LaLa Windows launcher. Automatically locate a compatible Python via "py" or PATH.
rem Double click to launch. CI: run_lala.bat --check [--py-only].

cd /d "%~dp0"
if errorlevel 1 goto :path_error

set "CHECK_ONLY=0"
set "PY_ONLY=0"
if /I "%~1"=="--check" set "CHECK_ONLY=1"
if /I "%~2"=="--py-only" set "PY_ONLY=1"
set "VENV_DIR=%CD%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "BASE_EXE="
set "BASE_ARG="

if exist "%VENV_PY%" goto :environment_ready

call :find_compatible_python
if not defined BASE_EXE goto :python_error

echo [LaLa] Detected Python: %BASE_EXE% %BASE_ARG%
echo [LaLa] Creating local Python environment...
"%BASE_EXE%" %BASE_ARG% -m venv "%VENV_DIR%"
if errorlevel 1 goto :venv_error

:environment_ready
if not exist "%VENV_PY%" goto :venv_error
rem Pillow 11.3.0 Windows binary wheels: Python 3.10 through 3.13.
"%VENV_PY%" -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>&1
if errorlevel 1 goto :venv_error
if not exist "requirements-desktop.txt" goto :requirements_error

rem Install only if the pinned dependency is missing; do not change system Python.
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

:find_compatible_python
rem Try Python Launcher registrations first. Do not use "py -3": it can select Python 3.15.
where py >nul 2>&1
if not errorlevel 1 (
    call :try_py_version 3.11
    call :try_py_version 3.12
    call :try_py_version 3.13
    call :try_py_version 3.10
)
if defined BASE_EXE exit /b 0
if "%PY_ONLY%"=="1" exit /b 0

rem Fall back to PATH when launcher is not installed or has no compatible Python.
where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>&1
    if not errorlevel 1 set "BASE_EXE=python"
)
if defined BASE_EXE exit /b 0

where python3 >nul 2>&1
if not errorlevel 1 (
    python3 -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>&1
    if not errorlevel 1 set "BASE_EXE=python3"
)
exit /b 0

:try_py_version
if defined BASE_EXE exit /b 0
py -%~1 -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>&1
if errorlevel 1 exit /b 0
set "BASE_EXE=py"
set "BASE_ARG=-%~1"
exit /b 0

:path_error
echo [LaLa] ERROR: Cannot open the folder containing run_lala.bat.
goto :failed

:python_error
echo [LaLa] ERROR: No compatible Python 3.10 - 3.13 was found.
echo [LaLa] Checked Python Launcher "py" and commands "python" / "python3".
echo [LaLa] Install Python 3.11 from https://www.python.org/downloads/
echo [LaLa] Verify with: py -0p
echo [LaLa] Then double click run_lala.bat again.
goto :failed

:venv_error
echo [LaLa] ERROR: Cannot use .venv\Scripts\python.exe.
echo [LaLa] Check installation, directory permissions and free space.
echo [LaLa] An old or incompatible .venv may exist. Rename it and retry.
goto :failed

:requirements_error
echo [LaLa] ERROR: requirements-desktop.txt was not found.
echo [LaLa] Extract the entire project ZIP before launching.
goto :failed

:install_error
echo [LaLa] ERROR: Unable to install Pillow.
echo [LaLa] Check network access or Python compatibility.
goto :failed

:launch_error
echo [LaLa] ERROR: The application could not start. Read the error above.
goto :failed

:failed
if "%CHECK_ONLY%"=="0" pause
exit /b 1
