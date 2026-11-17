#!/usr/bin/env bash
# Uses the Android phone (WebCam ADB app) as a Linux webcam + microphone.
#   video -> v4l2loopback /dev/video10 "Android Cam"
#   audio -> PipeWire virtual source "Android Mic"
#
#   ./webcam.sh                      # USB/ADB, back camera, 1280x720@30
#   ./webcam.sh -c front -r 1920x1080 --fps 30 --bitrate 8
#   ./webcam.sh --rotate 180 --mirror
#   ./webcam.sh --wifi 192.168.1.50  # over Wi-Fi (open the app on the phone)
#   ./webcam.sh --preview            # also open a preview window
#   ./webcam.sh --stop               # stop the app on the phone
set -uo pipefail
cd "$(dirname "$0")"

PKG=com.webcam.adb
PORT=8554
APORT=8555
HPORT=8556
CAMERA=back
RES=1280x720
FPS=30
BITRATE=6
ROTATE=0
MIRROR=0
WIFI=""
DEVNR=10
PIXFMT=yuv420p
PREVIEW=0
AUDIO=1
SERIAL=""

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; cat <<EOF

Options:
  -c, --camera back|front     camera (default: $CAMERA)
  -r, --res WxH               resolution (default: $RES)
      --fps N                 frames per second (default: $FPS)
      --bitrate MBPS          H.264 bitrate in Mbps (default: $BITRATE)
      --rotate 0|90|180|270   rotate image clockwise (default: $ROTATE)
      --mirror                flip horizontally
      --no-audio              don't create the "Android Mic" microphone
      --wifi IP               connect over Wi-Fi instead of USB
      --device N              /dev/videoN for v4l2loopback (default: $DEVNR)
      --pixfmt FMT            output pixel format: yuv420p | yuyv422 (default: $PIXFMT)
      --preview               show preview window (reads back from /dev/videoN)
  -s, --serial SERIAL         adb device serial
      --stop                  stop the app on the phone and exit
EOF
}

STOP=0
while [ $# -gt 0 ]; do
  case "$1" in
    -c|--camera) CAMERA="$2"; shift ;;
    -r|--res) RES="$2"; shift ;;
    --fps) FPS="$2"; shift ;;
    --bitrate) BITRATE="$2"; shift ;;
    --rotate) ROTATE="$2"; shift ;;
    --mirror) MIRROR=1 ;;
    --no-audio) AUDIO=0 ;;
    --wifi) WIFI="$2"; shift ;;
    --device) DEVNR="$2"; shift ;;
    --pixfmt) PIXFMT="$2"; shift ;;
    --preview) PREVIEW=1 ;;
    -s|--serial) SERIAL="$2"; shift ;;
    --stop) STOP=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Opción desconocida: $1"; usage; exit 1 ;;
  esac
  shift
done

ADB=(adb)
[ -n "$SERIAL" ] && ADB=(adb -s "$SERIAL")
DEV=/dev/video$DEVNR
W=${RES%x*}; H=${RES#*x}

if [ "$STOP" = 1 ]; then
  "${ADB[@]}" shell am start -n "$PKG/.MainActivity" --ez stop true >/dev/null
  for p in $PORT $APORT $HPORT; do "${ADB[@]}" forward --remove tcp:$p 2>/dev/null; done
  echo "App detenida."
  exit 0
fi

# --- v4l2loopback ---------------------------------------------------------
load_loopback() {
  sudo modprobe v4l2loopback devices=1 video_nr="$DEVNR" card_label="Android Cam" exclusive_caps=1
}
if [ ! -e "$DEV" ] || ! grep -qi "Android Cam\|loopback" "/sys/class/video4linux/video$DEVNR/name" 2>/dev/null; then
  if lsmod | grep -q '^v4l2loopback'; then
    if command -v v4l2loopback-ctl >/dev/null; then
      echo "Creando $DEV con v4l2loopback-ctl (sudo)..."
      sudo v4l2loopback-ctl add -n "Android Cam" --exclusive-caps=1 "$DEV" || exit 1
    else
      echo "v4l2loopback cargado pero sin $DEV. Ejecuta: sudo modprobe -r v4l2loopback"
      exit 1
    fi
  else
    echo "Cargando v4l2loopback en $DEV (sudo)..."
    load_loopback || exit 1
  fi
  sleep 1
fi
# v4l2loopback 0.12.x bug: a writer using write() (ffmpeg) is never flagged as writer,
# so after it closes the device stops announcing "Video Output". A dummy
# VIDIOC_STREAMON(OUTPUT) flags the opener as writer and close() restores it. No sudo.
unstick() {
  python3 -I -c '
import os, sys, fcntl, struct
fd = os.open(sys.argv[1], os.O_RDWR)
try: fcntl.ioctl(fd, 0x40045612, struct.pack("i", 2))  # VIDIOC_STREAMON, OUTPUT
except OSError: pass
os.close(fd)' "$DEV" 2>/dev/null
}
has_caps() { v4l2-ctl -d "$DEV" -D 2>/dev/null | grep -qE 'Video (Output|Capture)'; }
if ! has_caps; then
  if fuser -s "$DEV" 2>/dev/null; then
    echo "Aviso: $DEV en uso por: $(fuser "$DEV" 2>&1)"
  else
    unstick
    if ! has_caps; then
      echo "$DEV en estado inválido, recargando v4l2loopback (sudo)..."
      sudo modprobe -r v4l2loopback && load_loopback || exit 1
      sleep 1
    fi
  fi
fi
echo "Cámara virtual: $DEV ($(cat /sys/class/video4linux/video$DEVNR/name 2>/dev/null))"

# --- phone side -----------------------------------------------------------
if [ -z "$WIFI" ]; then
  state=$("${ADB[@]}" get-state 2>&1)
  if [ "$state" != "device" ]; then
    echo "ADB: '$state'. Conecta el teléfono y acepta 'Permitir depuración USB'."
    exit 1
  fi
  if ! "${ADB[@]}" shell pm path "$PKG" >/dev/null 2>&1; then
    [ -f WebCam.apk ] || ./build.sh || exit 1
    echo "Instalando WebCam.apk..."
    "${ADB[@]}" install -r WebCam.apk || exit 1
  fi
  for perm in CAMERA RECORD_AUDIO POST_NOTIFICATIONS; do
    "${ADB[@]}" shell pm grant "$PKG" android.permission.$perm 2>/dev/null
  done
  for p in $PORT $APORT $HPORT; do "${ADB[@]}" forward tcp:$p tcp:$p >/dev/null || exit 1; done
  "${ADB[@]}" shell input keyevent KEYCODE_WAKEUP
  "${ADB[@]}" shell am start -n "$PKG/.MainActivity" \
    --es camera "$CAMERA" --ei width "$W" --ei height "$H" \
    --ei fps "$FPS" --ei bitrate "$((BITRATE * 1000000))" --ez audio "$([ $AUDIO = 1 ] && echo true || echo false)" >/dev/null
  HOST=127.0.0.1
  echo "Visor web: http://127.0.0.1:$HPORT"
else
  HOST="$WIFI"
  echo "Visor web: http://$HOST:$HPORT"
fi

# --- filters --------------------------------------------------------------
VF=()
case "$ROTATE" in
  0) ;;
  90) VF+=("transpose=1") ;;
  180) VF+=("hflip,vflip") ;;
  270) VF+=("transpose=2") ;;
  *) echo "rotate inválido: $ROTATE"; exit 1 ;;
esac
[ "$MIRROR" = 1 ] && VF+=("hflip")
# fixed output size: loopback format cannot change while the device is open
case "$ROTATE" in 90|270) VF+=("scale=$H:$W") ;; *) VF+=("scale=$W:$H") ;; esac
VF+=("format=$PIXFMT")
FILTER=$(IFS=,; echo "${VF[*]}")

# Reconnecting TCP reader -> stdout (keeps consumers open across reconnects).
reader() { # port label
  while true; do
    if exec 3<>"/dev/tcp/$HOST/$1" 2>/dev/null; then
      echo "[$2] conectado" >&2
      cat <&3
      exec 3<&-
      echo "[$2] conexión perdida, reintentando..." >&2
    fi
    sleep 1
  done
}

LOOP_PID=""
cleanup() {
  trap - EXIT
  trap '' INT TERM   # survive our own "kill 0" so we can restore the device
  echo; echo "Saliendo..."
  [ -n "$LOOP_PID" ] && kill "$LOOP_PID" 2>/dev/null
  kill 0 2>/dev/null
  sleep 0.3
  unstick
  [ -n "${FIFO:-}" ] && rm -f "$FIFO"
  exit 0
}
trap cleanup INT TERM EXIT

# --- audio: PipeWire virtual microphone ------------------------------------
# module-pipe-tunnel exposes a FIFO as an Audio/Source node. No playback stream is
# involved, so tools like EasyEffects can't hijack it to the speakers.
if [ "$AUDIO" = 1 ]; then
  if command -v pw-cli >/dev/null; then
    FIFO="${XDG_RUNTIME_DIR:-/tmp}/androidmic-$$.fifo"
    rm -f "$FIFO"
    pw-cli -m load-module libpipewire-module-pipe-tunnel "{ tunnel.mode=source pipe.filename=\"$FIFO\"
      audio.format=S16LE audio.rate=48000 audio.channels=1 audio.position=[MONO]
      stream.props={ node.name=AndroidMic node.description=\"Android Mic\" } }" >/dev/null 2>&1 &
    LOOP_PID=$!
    for _ in $(seq 20); do [ -p "$FIFO" ] && break; sleep 0.2; done
    if [ -p "$FIFO" ]; then
      reader "$APORT" audio > "$FIFO" &
      echo "Micrófono virtual: \"Android Mic\""
    else
      echo "Aviso: no se pudo crear el micrófono virtual (PipeWire)."
    fi
  else
    echo "Aviso: sin PipeWire (pw-cli), audio desactivado."
  fi
fi

# --- video ----------------------------------------------------------------
echo "Transmitiendo tcp://$HOST:$PORT -> $DEV  (Ctrl+C para salir)"
if [ "$PREVIEW" = 1 ]; then
  (
    for _ in $(seq 30); do
      v4l2-ctl -d "$DEV" -D 2>/dev/null | grep -q 'Video Capture' && break
      sleep 1
    done
    ffplay -hide_banner -loglevel error -fflags nobuffer -window_title "Android Cam ($DEV)" -f v4l2 -i "$DEV"
  ) &
fi

reader "$PORT" video | ffmpeg -hide_banner -loglevel error -fflags nobuffer+discardcorrupt -flags low_delay \
  -probesize 32 -analyzeduration 0 -framerate "$FPS" -f h264 -i pipe:0 \
  -vf "$FILTER" -fps_mode passthrough -f v4l2 "$DEV"
echo "ffmpeg terminó (código $?)."
