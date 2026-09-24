@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 run.py
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python 3.10+ is required. Install from https://www.python.org/downloads/windows/
        pause
        exit /b 1
    )
    python run.py
)
if errorlevel 1 pause
