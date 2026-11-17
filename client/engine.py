#!/usr/bin/env python3
"""
PocketLens — engine (no GUI): adb, phone API, virtual camera/mic sinks, stream workers.

Connects to the PocketLens Android app (USB via adb, or Wi-Fi) and exposes the
phone camera as a virtual webcam (+ microphone):

  Linux   : video -> v4l2loopback (/dev/videoN)      audio -> PipeWire source "Android Mic"
  Windows : video -> OBS Virtual Camera (needs OBS)  audio -> any output device (e.g. VB-Cable)
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import av
import numpy as np
import pyvirtualcam

try:
    import sounddevice as sd  # Windows wheels bundle PortAudio; optional on Linux
except Exception:  # noqa: BLE001
    sd = None

APP_NAME = "PocketLens"
PKG = "com.webcam.adb"
PORT_VIDEO, PORT_AUDIO, PORT_HTTP = 8554, 8555, 8556
AUDIO_RATE = 48000
IS_WIN = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")
NO_WINDOW = 0x08000000 if IS_WIN else 0  # CREATE_NO_WINDOW

RESOLUTIONS = ["640x480", "1280x720", "1920x1080"]
FPS_LIST = ["15", "24", "30", "60"]
BITRATES = ["2", "4", "6", "8", "12", "16"]
ROTATIONS = ["0", "90", "180", "270"]


def base_dir() -> Path:
    """Directory of the script, or of the executable when frozen with PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def config_path() -> Path:
    if IS_WIN:
        root = Path(os.environ.get("APPDATA", Path.home()))
        return root / "WebCamADB" / "client.json"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "webcam-adb" / "client.json"


# =============================================================================
# ADB
# =============================================================================

def find_adb() -> str | None:
    exe = "adb.exe" if IS_WIN else "adb"
    candidates = [os.environ.get("ADB")]
    candidates.append(shutil.which("adb"))
    for d in (base_dir(), base_dir().parent):
        candidates += [str(d / "platform-tools" / exe), str(d / exe)]
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(env):
            candidates.append(str(Path(os.environ[env]) / "platform-tools" / exe))
    if IS_WIN and os.environ.get("LOCALAPPDATA"):
        candidates.append(str(Path(os.environ["LOCALAPPDATA"]) / "Android" / "Sdk" / "platform-tools" / exe))
    candidates.append(str(Path.home() / "Android" / "Sdk" / "platform-tools" / exe))
    for c in candidates:
        if c and Path(c).is_file():
            return c
    return None


def find_apk() -> Path | None:
    for d in (base_dir(), base_dir().parent):
        p = d / "WebCam.apk"
        if p.is_file():
            return p
    return None


class Adb:
    def __init__(self, path: str):
        self.path = path

    def run(self, *args: str, serial: str | None = None, timeout: float = 15) -> subprocess.CompletedProcess:
        cmd = [self.path] + (["-s", serial] if serial else []) + list(args)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW)

    def devices(self) -> list[tuple[str, str, str]]:
        """[(serial, state, model)]"""
        try:
            out = self.run("devices", "-l", timeout=8).stdout
        except Exception:  # noqa: BLE001
            return []
        res = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 2:
                continue
            model = next((p.split(":", 1)[1] for p in parts[2:] if p.startswith("model:")), "")
            res.append((parts[0], parts[1], model))
        return res


# =============================================================================
# Phone HTTP API (bypasses any http_proxy env, e.g. Burp)
# =============================================================================

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def phone_api(host: str, path: str, params: dict | None = None, timeout: float = 3) -> dict | None:
    url = f"http://{host}:{PORT_HTTP}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with _opener.open(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


# =============================================================================
# Linux v4l2loopback helpers
# =============================================================================

VIDIOC_QUERYCAP = 0x80685600
VIDIOC_STREAMON = 0x40045612
V4L2_BUF_TYPE_VIDEO_OUTPUT = 2
CAP_VIDEO_CAPTURE, CAP_VIDEO_OUTPUT = 0x1, 0x2


def loopback_devices() -> list[tuple[str, str]]:
    """[(/dev/videoN, name)] of v4l2loopback devices (they live under /sys/devices/virtual)."""
    res = []
    root = Path("/sys/class/video4linux")
    if not root.exists():
        return res
    for d in sorted(root.iterdir(), key=lambda p: int("".join(c for c in p.name if c.isdigit()) or 0)):
        if "/virtual/" in os.path.realpath(d):
            name = (d / "name").read_text().strip() if (d / "name").exists() else d.name
            res.append((f"/dev/{d.name}", name))
    return res


def device_caps(dev: str) -> int:
    import fcntl
    buf = bytearray(104)
    fd = os.open(dev, os.O_RDWR | os.O_NONBLOCK)
    try:
        fcntl.ioctl(fd, VIDIOC_QUERYCAP, buf)
    finally:
        os.close(fd)
    return struct.unpack_from("<I", buf, 88)[0]  # device_caps


def unstick_loopback(dev: str) -> None:
    """v4l2loopback 0.12.x: writers using write() are never flagged as writers, so after
    they close the device stops announcing VIDEO_OUTPUT. A dummy STREAMON(OUTPUT) flags
    this opener as writer and close() restores it."""
    import fcntl
    try:
        fd = os.open(dev, os.O_RDWR | os.O_NONBLOCK)
    except OSError:
        return
    try:
        fcntl.ioctl(fd, VIDIOC_STREAMON, struct.pack("i", V4L2_BUF_TYPE_VIDEO_OUTPUT))
    except OSError:
        pass
    finally:
        os.close(fd)


def prepare_loopback(preferred: str | None) -> str | None:
    devs = loopback_devices()
    if not devs:
        return None
    paths = [d for d, _ in devs]
    dev = preferred if preferred in paths else next((d for d, n in devs if "Android" in n), paths[0])
    try:
        if not device_caps(dev) & (CAP_VIDEO_OUTPUT | CAP_VIDEO_CAPTURE):
            unstick_loopback(dev)
    except OSError:
        pass
    return dev


def load_loopback_module() -> bool:
    cmd = ["pkexec", "modprobe", "v4l2loopback", "devices=1", "video_nr=10",
           "card_label=Android Cam", "exclusive_caps=1"]
    try:
        return subprocess.run(cmd, timeout=120).returncode == 0
    except Exception:  # noqa: BLE001
        return False


# =============================================================================
# Audio sinks
# =============================================================================

class PipeWireSource:
    """Virtual microphone via PipeWire module-pipe-tunnel (reads a FIFO). No playback stream,
    so EasyEffects & co. can't reroute it. Non-blocking writes: if nobody records, data is
    dropped instead of piling up latency."""
    name = "Android Mic"

    def __init__(self):
        rt = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
        self.fifo = f"{rt}/androidmic-{os.getpid()}.fifo"
        if os.path.exists(self.fifo):
            os.unlink(self.fifo)
        args = ("{ tunnel.mode=source pipe.filename=\"%s\" audio.format=S16LE audio.rate=%d "
                "audio.channels=1 audio.position=[MONO] stream.props={ node.name=AndroidMic "
                "node.description=\"Android Mic\" } }" % (self.fifo, AUDIO_RATE))
        self.proc = subprocess.Popen(["pw-cli", "-m", "load-module", "libpipewire-module-pipe-tunnel", args],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            if os.path.exists(self.fifo):
                break
            time.sleep(0.1)
        else:
            self.close()
            raise RuntimeError("PipeWire no creó el micrófono virtual")
        time.sleep(0.2)
        self.fd = os.open(self.fifo, os.O_WRONLY | os.O_NONBLOCK)
        try:
            import fcntl
            fcntl.fcntl(self.fd, 1031, 16384)  # F_SETPIPE_SZ: ~170 ms max buffer
        except OSError:
            pass

    def write(self, data: bytes) -> None:
        try:
            os.write(self.fd, data)
        except BlockingIOError:
            pass  # nobody is recording: drop
        except OSError:
            pass

    def close(self) -> None:
        try:
            os.close(self.fd)
        except Exception:  # noqa: BLE001
            pass
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        try:
            os.unlink(self.fifo)
        except OSError:
            pass


class SoundDeviceSink:
    """Plays phone audio to an output device (on Windows pick 'CABLE Input' from VB-Cable)."""

    def __init__(self, device_index: int | None):
        self.stream = sd.RawOutputStream(samplerate=AUDIO_RATE, channels=1, dtype="int16",
                                         device=device_index, latency="low", blocksize=960)
        self.stream.start()
        info = sd.query_devices(device_index if device_index is not None else sd.default.device[1])
        self.name = info["name"]

    def write(self, data: bytes) -> None:
        if self.stream.write_available * 2 < len(data):
            return  # avoid latency build-up
        self.stream.write(data)

    def close(self) -> None:
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:  # noqa: BLE001
            pass


def output_devices() -> list[tuple[int, str]]:
    if sd is None:
        return []
    try:
        hostapis = sd.query_hostapis()
        res = []
        for i, d in enumerate(sd.query_devices()):
            if d["max_output_channels"] > 0:
                api = hostapis[d["hostapi"]]["name"]
                if IS_WIN and "MME" not in api:
                    continue  # one entry per device
                res.append((i, d["name"]))
        return res
    except Exception:  # noqa: BLE001
        return []


def pipewire_available() -> bool:
    return IS_LINUX and shutil.which("pw-cli") is not None


# =============================================================================
# Workers
# =============================================================================

class VideoWorker(threading.Thread):
    def __init__(self, host: str, width: int, height: int, fps: int, rotate: int, mirror: bool, device: str | None):
        super().__init__(daemon=True, name="video")
        self.host, self.fps, self.rotate, self.mirror, self.device = host, fps, rotate, mirror, device
        # decoded size before rotation; virtual camera size after rotation
        self.src_w, self.src_h = width, height
        self.out_w, self.out_h = (height, width) if rotate in (90, 270) else (width, height)
        self.stop_ev = threading.Event()
        self.state = "Iniciando…"
        self.connected = False
        self.cam_name = ""
        self.stat_fps = 0.0
        self.latest: np.ndarray | None = None
        self.frame_id = 0
        self.error: str | None = None
        self.sock: socket.socket | None = None

    def stop(self) -> None:
        self.stop_ev.set()
        s = self.sock
        if s:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _transform(self, rgb: np.ndarray) -> np.ndarray:
        if self.rotate == 90:
            rgb = np.rot90(rgb, k=-1)
        elif self.rotate == 180:
            rgb = rgb[::-1, ::-1]
        elif self.rotate == 270:
            rgb = np.rot90(rgb, k=1)
        if self.mirror:
            rgb = rgb[:, ::-1]
        return np.ascontiguousarray(rgb)

    def run(self) -> None:
        try:
            kw = {"device": self.device} if self.device else {}
            cam = pyvirtualcam.Camera(self.out_w, self.out_h, self.fps, fmt=pyvirtualcam.PixelFormat.RGB, **kw)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if IS_WIN and ("obs" in msg.lower() or "backend" in msg.lower()):
                msg = "No se encontró OBS Virtual Camera. Instala OBS Studio (https://obsproject.com) — no hace falta abrirlo.\n\n" + msg
            self.error = msg
            self.state = "Error de cámara virtual"
            return
        self.cam_name = cam.device
        black = np.zeros((self.out_h, self.out_w, 3), np.uint8)
        try:
            while not self.stop_ev.is_set():
                self.connected = False
                self.state = "Conectando…"
                try:
                    self._stream(cam)
                except Exception as e:  # noqa: BLE001
                    if not self.stop_ev.is_set():
                        self.state = f"Reconectando… ({e.__class__.__name__})"
                self.connected = False
                self.stat_fps = 0
                # keep consumers alive with black frames while reconnecting
                for _ in range(5):
                    if self.stop_ev.is_set():
                        break
                    cam.send(black)
                    time.sleep(0.2)
        finally:
            cam.close()
            if IS_LINUX and self.cam_name:
                time.sleep(0.1)
                unstick_loopback(self.cam_name)

    def _stream(self, cam) -> None:
        s = socket.create_connection((self.host, PORT_VIDEO), timeout=4)
        s.settimeout(5)
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock = s
        codec = av.CodecContext.create("h264", "r")
        codec.thread_type = "SLICE"
        codec.options = {"flags": "low_delay"}
        frames, t0 = 0, time.monotonic()
        try:
            while not self.stop_ev.is_set():
                data = s.recv(1 << 16)
                if not data:
                    raise ConnectionError("cerrado")
                for pkt in codec.parse(data):
                    try:
                        decoded = codec.decode(pkt)
                    except av.error.InvalidDataError:
                        continue
                    for frame in decoded:
                        rgb = frame.reformat(width=self.src_w, height=self.src_h, format="rgb24").to_ndarray()
                        rgb = self._transform(rgb)
                        cam.send(rgb)
                        self.latest = rgb
                        self.frame_id += 1
                        frames += 1
                        if not self.connected:
                            self.connected = True
                            self.state = "Conectado"
                now = time.monotonic()
                if now - t0 >= 1:
                    self.stat_fps = frames / (now - t0)
                    frames, t0 = 0, now
        finally:
            self.sock = None
            s.close()


class AudioWorker(threading.Thread):
    def __init__(self, host: str, sink):
        super().__init__(daemon=True, name="audio")
        self.host, self.sink = host, sink
        self.stop_ev = threading.Event()
        self.connected = False
        self.sock: socket.socket | None = None

    def stop(self) -> None:
        self.stop_ev.set()
        s = self.sock
        if s:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def run(self) -> None:
        try:
            while not self.stop_ev.is_set():
                try:
                    s = socket.create_connection((self.host, PORT_AUDIO), timeout=4)
                    s.settimeout(5)
                    self.sock = s
                    try:
                        while not self.stop_ev.is_set():
                            data = s.recv(3840)
                            if not data:
                                break
                            self.connected = True
                            if len(data) % 2:
                                data += s.recv(1)
                            self.sink.write(data)
                    finally:
                        self.sock = None
                        s.close()
                except Exception:  # noqa: BLE001
                    pass
                self.connected = False
                self.stop_ev.wait(1.5)
        finally:
            self.sink.close()


class StatusPoller(threading.Thread):
    def __init__(self, host: str):
        super().__init__(daemon=True, name="status")
        self.host = host
        self.stop_ev = threading.Event()
        self.status: dict | None = None

    def run(self) -> None:
        while not self.stop_ev.is_set():
            self.status = phone_api(self.host, "/api/status", timeout=2)
            self.stop_ev.wait(1)


# =============================================================================
# LAN discovery (phone broadcasts a UDP beacon every 2 s)
# =============================================================================

PORT_DISCOVERY = 8557


class Discovery(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="discovery")
        self.found: dict[str, dict] = {}
        self.stop_ev = threading.Event()
        self.error: str | None = None

    def run(self) -> None:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        try:
            s.bind(("", PORT_DISCOVERY))
        except OSError as e:
            self.error = str(e)
            return
        s.settimeout(1)
        while not self.stop_ev.is_set():
            try:
                data, (ip, _) = s.recvfrom(2048)
                msg = json.loads(data.decode("utf-8"))
                if msg.get("app") == "webcam-adb":
                    msg["seen"] = time.monotonic()
                    self.found[ip] = msg
            except (socket.timeout, ValueError):
                pass
            except OSError:
                break
        s.close()

    def phones(self) -> list[tuple[str, dict]]:
        now = time.monotonic()
        return sorted(((ip, m) for ip, m in list(self.found.items()) if now - m["seen"] < 7), key=lambda x: x[0])


# =============================================================================
# Versioning & updates (GitHub Releases)
# =============================================================================

def _bundled_file(name: str) -> Path | None:
    for d in (getattr(sys, "_MEIPASS", None), base_dir(), base_dir().parent):
        if d and (Path(d) / name).is_file():
            return Path(d) / name
    return None


def _read_bundled(name: str, default: str) -> str:
    p = _bundled_file(name)
    try:
        return p.read_text().strip() if p else default
    except OSError:
        return default


APP_VERSION = _read_bundled("VERSION", "0.0.0")
REPO = _read_bundled("REPO", "CamiloFerreira/pocketlens")
RELEASES_URL = f"https://github.com/{REPO}/releases"


def parse_version(v: str) -> tuple[int, int, int]:
    import re
    nums = [int(x) for x in re.findall(r"\d+", v.lstrip("vV"))[:3]]
    return tuple(nums + [0] * (3 - len(nums)))  # type: ignore[return-value]


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def _http_get(url: str, timeout: float = 10):
    req = urllib.request.Request(url, headers={"User-Agent": f"PocketLens-Desktop/{APP_VERSION}",
                                               "Accept": "application/vnd.github+json",
                                               "Cache-Control": "no-cache"})
    try:  # direct first (ignores debugging proxies like Burp in http(s)_proxy)
        return _opener.open(req, timeout=timeout)
    except Exception:  # noqa: BLE001
        return urllib.request.urlopen(req, timeout=timeout)


def latest_release() -> dict | None:
    """{'version', 'notes', 'page', 'assets': {name: url}} or None on error."""
    try:
        with _http_get(f"https://api.github.com/repos/{REPO}/releases/latest") as r:
            j = json.loads(r.read().decode("utf-8"))
        return {"version": j["tag_name"].lstrip("vV"), "notes": j.get("body") or "", "page": j.get("html_url", ""),
                "assets": {a["name"]: a["browser_download_url"] for a in j.get("assets", [])}}
    except Exception:  # noqa: BLE001
        return None


def pick_asset(assets: dict, kind: str) -> str | None:
    """kind: 'apk' | 'self' (binary for this OS) | 'deb'"""
    for name, url in assets.items():
        n = name.lower()
        if kind == "apk" and n.endswith(".apk"):
            return url
        if kind == "deb" and n.endswith("_amd64.deb"):
            return url
        if kind == "self" and IS_WIN and n.endswith(".exe"):
            return url
        if kind == "self" and IS_LINUX and "linux" in n and not n.endswith((".tar.gz", ".zip", ".sha256", ".deb")):
            return url
    return None


def download(url: str, dest: Path, progress=None) -> Path:
    with _http_get(url, timeout=30) as r:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        with open(dest, "wb") as f:
            while True:
                b = r.read(1 << 16)
                if not b:
                    break
                f.write(b)
                got += len(b)
                if progress and total:
                    progress(int(got * 100 / total))
    return dest


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def source_checkout() -> Path | None:
    root = Path(__file__).resolve().parent.parent
    return root if (root / ".git").exists() else None


def install_mode() -> str:
    """'deb' (installed package in /opt/pocketlens), 'binary' (standalone), or 'source'."""
    if not is_frozen():
        return "source"
    exe = Path(sys.executable).resolve()
    if IS_LINUX and str(exe).startswith("/opt/pocketlens/") and not os.access(exe.parent, os.W_OK):
        return "deb"
    return "binary"


def can_self_update(assets: dict) -> bool:
    mode = install_mode()
    if mode == "deb":
        return pick_asset(assets, "deb") is not None and shutil.which("pkexec") is not None
    if mode == "binary":
        return pick_asset(assets, "self") is not None
    return source_checkout() is not None


def self_update(assets: dict, progress=None) -> None:
    """Replace this program with the latest release. Call restart() afterwards."""
    if install_mode() == "deb":
        import tempfile
        url = pick_asset(assets, "deb")
        if not url:
            raise RuntimeError("El release no incluye paquete .deb.")
        deb = Path(tempfile.gettempdir()) / url.rsplit("/", 1)[-1]
        download(url, deb, progress)
        deb.chmod(0o644)
        r = subprocess.run(["pkexec", "apt-get", "install", "-y", "--allow-downgrades", str(deb)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("No se pudo instalar el paquete:\n" + (r.stderr or r.stdout).strip()[-600:])
        return
    if is_frozen():
        url = pick_asset(assets, "self")
        if not url:
            raise RuntimeError("No hay binario para esta plataforma en el release.")
        exe = Path(sys.executable).resolve()
        tmp = exe.with_name(exe.name + ".new")
        download(url, tmp, progress)
        if IS_WIN:  # a running .exe can be renamed but not overwritten
            old = exe.with_name(exe.name + ".old")
            if old.exists():
                old.unlink()
            exe.rename(old)
            tmp.rename(exe)
        else:
            tmp.chmod(0o755)
            os.replace(tmp, exe)
        return
    root = source_checkout()
    if not root:
        raise RuntimeError("Instalación sin git: descarga la nueva versión desde " + RELEASES_URL)
    r = subprocess.run(["git", "-C", str(root), "pull", "--ff-only"], capture_output=True, text=True,
                       creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError("git pull falló:\n" + (r.stderr or r.stdout))
    req = Path(__file__).resolve().parent / "requirements.txt"
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(req)], creationflags=NO_WINDOW)


def restart() -> None:
    if is_frozen():
        subprocess.Popen([sys.executable] + sys.argv[1:], creationflags=NO_WINDOW)
    else:
        subprocess.Popen([sys.executable] + sys.argv, creationflags=NO_WINDOW)


def cleanup_old_binary() -> None:
    if is_frozen():
        old = Path(sys.executable).with_name(Path(sys.executable).name + ".old")
        try:
            old.unlink(missing_ok=True)
        except OSError:
            pass


def update_phone_app(adb: "Adb", serial: str, apk_url: str, progress=None, allow_reinstall: bool = False) -> str:
    """Download the release APK and install it over USB. Returns 'ok' or 'signature' (needs reinstall)."""
    import tempfile
    dest = Path(tempfile.gettempdir()) / "PocketLens-update.apk"
    download(apk_url, dest, progress)
    r = adb.run("install", "-r", str(dest), serial=serial, timeout=240)
    out = (r.stdout + r.stderr)
    if r.returncode == 0 and "Success" in out:
        return "ok"
    if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in out or "signatures do not match" in out.lower():
        if not allow_reinstall:
            return "signature"
        adb.run("uninstall", PKG, serial=serial, timeout=60)
        r = adb.run("install", str(dest), serial=serial, timeout=240)
        if r.returncode == 0:
            return "ok"
        out = r.stdout + r.stderr
    raise RuntimeError("adb install falló: " + out.strip()[-400:])
