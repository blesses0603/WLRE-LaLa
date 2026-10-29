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
rem Pillow 13.0.0 requires Python 3.11 through 3.15.
"%VENV_PY%" -c "import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 15) else 1)" >nul 2>&1
if errorlevel 1 goto :venv_error
"%VENV_PY%" -c "import tkinter" >nul 2>&1
if errorlevel 1 goto :tk_error
if not exist "requirements-desktop.txt" goto :requirements_error

rem Install only if the pinned dependency is missing; do not change system Python.
"%VENV_PY%" -c "import PIL, tkinter; from PIL import Image, ImageTk; assert PIL.__version__ == '13.0.0'" >nul 2>&1
if errorlevel 1 (
    echo [LaLa] Installing desktop image dependency. Internet may be required.
    "%VENV_PY%" -m pip --disable-pip-version-check install --only-binary=:all: -r "requirements-desktop.txt"
    if errorlevel 1 goto :install_error
)
"%VENV_PY%" -c "import PIL, tkinter; from PIL import Image, ImageTk; assert PIL.__version__ == '13.0.0'" >nul 2>&1
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
rem Use the default Python 3 interpreter if supported, including Python 3.14/3.15.
rem If the default is too new or broken, try registered compatible versions.
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 15) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "BASE_EXE=py"
        set "BASE_ARG=-3"
    )
    if not defined BASE_EXE call :try_py_version 3.15
    if not defined BASE_EXE call :try_py_version 3.14
    if not defined BASE_EXE call :try_py_version 3.13
    if not defined BASE_EXE call :try_py_version 3.12
    if not defined BASE_EXE call :try_py_version 3.11
)
if defined BASE_EXE exit /b 0
if "%PY_ONLY%"=="1" exit /b 0

rem Fall back to PATH when launcher is not installed or has no compatible Python.
where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 15) else 1)" >nul 2>&1
    if not errorlevel 1 set "BASE_EXE=python"
)
if defined BASE_EXE exit /b 0

where python3 >nul 2>&1
if not errorlevel 1 (
    python3 -c "import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 15) else 1)" >nul 2>&1
    if not errorlevel 1 set "BASE_EXE=python3"
)
exit /b 0

:try_py_version
if defined BASE_EXE exit /b 0
py -%~1 -c "import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 15) else 1)" >nul 2>&1
if errorlevel 1 exit /b 0
set "BASE_EXE=py"
set "BASE_ARG=-%~1"
exit /b 0

:path_error
echo [LaLa] ERROR: Cannot open the folder containing run_lala.bat.
goto :failed

:python_error
echo [LaLa] ERROR: Pillow 13 requires Python 3.11 - 3.15.
echo [LaLa] Checked Python Launcher "py" and commands "python" / "python3".
echo [LaLa] Python 3.10 is not supported by Pillow 13.
echo [LaLa] Python may be installed but unregistered or outside supported versions.
echo [LaLa] See https://www.python.org/downloads/
echo [LaLa] Check versions: py -0p
echo [LaLa] Check default: py -3 --version
echo [LaLa] Check paths: where py
echo [LaLa] Then double click run_lala.bat again.
goto :failed

:venv_error
echo [LaLa] ERROR: Cannot use .venv\Scripts\python.exe.
echo [LaLa] Check installation, directory permissions and free space.
echo [LaLa] An old Python 3.10 or broken .venv may exist.
echo [LaLa] Rename .venv and retry. The launcher does not delete it.
goto :failed

:tk_error
echo [LaLa] ERROR: Python is missing Tkinter support.
echo [LaLa] Install Python with Tcl/Tk and retry.
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
