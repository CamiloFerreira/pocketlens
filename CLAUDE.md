# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

PocketLens: Android phone as webcam + microphone for Linux/Windows. Public repo `CamiloFerreira/pocketlens` (see `REPO`). UI strings, changelog and docs are in Spanish.

## Commands

```bash
./build.sh                    # Android APK without Gradle (SDK build-tools + JDK) -> WebCam.apk
adb install -r WebCam.apk     # install on phone (package com.webcam.adb)
client/run.sh                 # desktop client from source (creates client/.venv)
client/build-linux.sh         # PyInstaller onefile -> client/dist/PocketLens-linux-x86_64
packaging/build-deb.sh        # .deb from that binary (+ WebCam.apk, webcam.sh)
client\build-windows.bat      # Windows exe (run on Windows)
./webcam.sh [--wifi IP] [--preview]   # headless Linux client (bash + ffmpeg), no Python
./scripts/release.sh X.Y.Z [--mandatory]   # publish a release (see below)
```

There is no test suite or linter config. Checks used in practice: `client/.venv/bin/python -m pyflakes client/*.py`, offscreen GUI smoke tests (`QT_QPA_PLATFORM=offscreen`, set `XDG_CONFIG_HOME` to a temp dir so the user's `~/.config/webcam-adb/client.json` is not overwritten), and live tests against the phone over USB after `adb forward tcp:855{4,5,6} tcp:855{4,5,6}`.

## Architecture

**Phone (`android/src/com/webcam/adb/`)** — `CamService` is a foreground service (camera|microphone) exposing:
- TCP 8554: H.264 Annex-B from a MediaCodec surface encoder (Camera2). Late clients wait for a keyframe.
- TCP 8555: mic PCM s16le 48 kHz mono.
- HTTP 8556: JSON control API (`/api/status|switch|torch|mic|zoom|exposure|focus|config`), MJPEG `/video`, `/snapshot.jpg`, web viewer (`WebPage`).
- UDP 8557: discovery beacon for Wi-Fi.
The camera only runs while a client is connected. `MainActivity` is the landscape UI. `Updater` self-updates from GitHub Releases via `PackageInstaller`. `build.sh` generates `BuildInfo.java` (VERSION, VERSION_CODE = MAJ*10000+MIN*100+PAT, REPO) from the root `VERSION`/`REPO` files.

**Desktop (`client/`)** — `engine.py` has no Qt: adb wrapper, phone API, `VideoWorker` (TCP H.264 → PyAV decode → rotate/mirror → optional background effect → pyvirtualcam), `AudioWorker` + sinks (Linux `PipeWireSource` = `libpipewire-module-pipe-tunnel` FIFO source "Android Mic"; Windows `SoundDeviceSink` to VB-Cable), Wi-Fi `Discovery`, v4l2loopback helpers, and update/self-update logic. `webcam_client.py` is the PySide6 GUI; workers are threads polled by QTimers (`_tick`, `_slow_tick`), and live settings are plain attributes set on the worker (`video.mirror`, `video.bg_mode`, …). `bgfilter.py` does person segmentation with MediaPipe Tasks (`assets/models/*.tflite`) in its own thread; composition uses the newest mask (≤1 frame old). Built-in backgrounds in `assets/backgrounds/` come from `make_backgrounds.py`.

## Non-obvious constraints

- **v4l2loopback 0.12.7 (Ubuntu)**: after a `write()`-based writer closes, the device can be stuck without `VIDEO_OUTPUT`. `unstick_loopback()` / `prepare_loopback()` fix it without sudo via a dummy `VIDIOC_STREAMON(OUTPUT)`. Always close the virtual camera through the worker so the unstick runs.
- **PyInstaller builds on Linux** set `LD_LIBRARY_PATH` to their bundled libs; `engine.py` restores it at import so system `adb`/`pw-cli`/`pkexec` work. Don't spawn external tools before `engine` is imported.
- **Child processes**: don't use `subprocess` `preexec_fn` (the client is heavily multithreaded and can deadlock). `pw-cli` is wrapped in `setpriv --pdeathsig TERM` so the virtual mic disappears if the client dies.
- **`Toggle` widget**: its Qt property is named `knob`, not `pos` (that would shadow `QWidget.pos`). It paints from `isChecked()`; the animation is cosmetic because it was observed not to tick on the user's Wayland session.
- **EasyEffects** reroutes normal playback streams, which is why the mic is a pipe-tunnel *source* and not a `pw-cat` stream.
- **Port 8080** is often taken (Burp Suite) and `http_proxy` may be set: the phone API uses a no-proxy opener on 8556.
- The release `.deb`/binary is built on ubuntu-22.04 in CI. It is about 270 MB because it bundles MediaPipe and OpenCV.

## Releases and updates

1. Add `## [X.Y.Z] - date` to `CHANGELOG.md`; the working tree must be clean.
2. `./scripts/release.sh X.Y.Z` bumps `VERSION`, commits and pushes. It then builds and signs the APK **locally** and creates the GitHub release with notes from the changelog.
3. GitHub Actions (`.github/workflows/release.yml`, on release published) builds the Linux binary, `.deb`, Windows exe and `SHA256SUMS.txt`, and attaches them to the release.

Signing key: `~/.android/pocketlens-release.jks` + `.pass` (alias `pocketlens`). It is never uploaded to CI. Losing it breaks Android updates.

`--mandatory` (security fixes) writes `MIN_VERSION`. Every release then carries `<!-- min-version: X.Y.Z -->` in its notes. Android apps below it disable the camera and mic and show a non-dismissable update dialog. Desktop clients below it refuse to connect, and they also refuse phones whose app is below it.

Installed apps poll `releases/latest`: Android hourly, desktop on start and every 6 h. Desktop self-update depends on how it was installed (`engine.install_mode()`): `.deb` via `pkexec apt-get install`, onefile binary by replacing itself, source checkout via `git pull`.

Only publish a release when the user explicitly asks for it.
