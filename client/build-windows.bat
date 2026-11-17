@echo off
rem Builds dist\PocketLens-windows-x64.exe (run on Windows with Python 3.10+).
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv || python -m venv .venv
)
.venv\Scripts\python -m pip install -q --upgrade pip
.venv\Scripts\python -m pip install -q -r requirements.txt pyinstaller
.venv\Scripts\pyinstaller --noconfirm --onefile --windowed --name PocketLens-windows-x64 --icon assets\icon.ico ^
  --add-data "assets:assets" --add-data "..\VERSION:." --add-data "..\REPO:." webcam_client.py || exit /b 1
echo OK -^> dist\PocketLens-windows-x64.exe
