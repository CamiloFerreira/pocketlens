#!/usr/bin/env bash
# Run the WebCam ADB client on Linux (creates a local venv on first run).
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/python webcam_client.py "$@"
