@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m lala_desktop
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [LaLa] Python 3 not found. Install Python 3.10 or later.
        pause
        exit /b 1
    )
    python -m lala_desktop
)
if errorlevel 1 (
    echo.
    echo [LaLa] Startup failed. See the error above.
    pause
    exit /b 1
)
endlocal
