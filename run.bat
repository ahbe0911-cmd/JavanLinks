@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv
    if errorlevel 1 goto fail
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -c "import PySide6.QtWebEngineWidgets" >nul 2>&1
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" main.py
if errorlevel 1 goto fail
exit /b 0
:fail
echo Launch failed. Install Python 3.11 or 3.12 x64 and check pip/network access.
pause
exit /b 1
