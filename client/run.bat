@echo off
rem Run the WebCam ADB client on Windows (creates a local venv on first run).
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\python -m pip install -q --upgrade pip
  .venv\Scripts\python -m pip install -q -r requirements.txt
)
start "" .venv\Scripts\pythonw.exe webcam_client.py
