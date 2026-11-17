#!/usr/bin/env bash
# Builds a standalone Linux binary: dist/PocketLens-linux-x86_64
set -e
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { python3 -m venv .venv; .venv/bin/pip install -q -r requirements.txt; }
.venv/bin/pip install -q pyinstaller
.venv/bin/pyinstaller --noconfirm --onefile --windowed --name PocketLens-linux-x86_64 \
  --icon assets/icon.ico --add-data "assets:assets" --add-data "../VERSION:." --add-data "../REPO:." \
  --exclude-module sounddevice webcam_client.py
echo "OK -> $(pwd)/dist/PocketLens-linux-x86_64"
