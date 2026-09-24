@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo AOA Whale Viewer v0.3.1 - verified launcher
echo Do not reuse the old browser tab. This launcher opens the verified new address.
where py >nul 2>nul
if not errorlevel 1 (
    py -3 run.py %*
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python 3.10+ is required. https://www.python.org/downloads/windows/
        pause
        exit /b 1
    )
    python run.py %*
)
if errorlevel 1 pause
