@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
  if not errorlevel 1 (
    py -3 app.py --open
    goto done
  )
)
python -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
if not errorlevel 1 (
  python app.py --open
  goto done
)
echo Python 3.10 or newer is required. Install Python from python.org and retry.
:done
echo.
echo If the app stopped unexpectedly, capture the error above.
pause
