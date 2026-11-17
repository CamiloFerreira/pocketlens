# PocketLens — cliente de escritorio (Linux y Windows)

Ventana con vista previa que conecta con la app del teléfono (USB por ADB o Wi-Fi) y
publica la cámara como webcam virtual, más el micrófono del teléfono.

| | Vídeo | Audio |
|---|---|---|
| Linux | v4l2loopback (`/dev/video10`, "Android Cam") | PipeWire, fuente "Android Mic" |
| Windows | "OBS Virtual Camera" | dispositivo de salida elegido (VB-Cable → "CABLE Output" como micro) |

Funciones:
- Dispositivos: lista de teléfonos por USB (adb) o **detectados automáticamente en la red Wi-Fi** (UDP 8557), o IP manual.
- Vídeo: cámara, resolución, FPS, calidad · Imagen: rotación, espejo (en vivo), dispositivo virtual · Audio: micrófono y salida.
- Vista previa con indicadores (EN VIVO, resolución, fps, Mbps) y barra flotante: cambiar cámara, linterna,
  silenciar micrófono, zoom, exposición, espejo, foto (en Imágenes), pantalla completa (F11 / doble clic).
- Icono en la bandeja: al cerrar la ventana sigue transmitiendo; salir desde el menú de la bandeja.
- Reconexión automática; pie con dispositivo virtual, audio, fps y tiempo conectado.
Recuerda la configuración (`~/.config/webcam-adb/client.json` / `%APPDATA%\WebCamADB\client.json`).

## Linux
Requisitos: `adb`, `v4l2loopback-dkms`, PipeWire (Ubuntu 22.04+ ya lo trae).
```bash
./run.sh                 # primera vez crea .venv e instala dependencias
./build-linux.sh         # binario único: dist/PocketLens-linux-x86_64
```
Si no existe la cámara virtual, el cliente ofrece cargar `v4l2loopback` (pide contraseña con pkexec).
Para que se cargue siempre al arrancar:
```bash
echo v4l2loopback | sudo tee /etc/modules-load.d/v4l2loopback.conf
echo 'options v4l2loopback devices=1 video_nr=10 card_label="Android Cam" exclusive_caps=1' | sudo tee /etc/modprobe.d/v4l2loopback.conf
```
En sesiones X11 (no Wayland) el binario necesita `sudo apt install libxcb-cursor0`.

Acceso directo en el menú:
```bash
sed "s|__DIR__|$PWD|" webcam-adb.desktop > ~/.local/share/applications/webcam-adb.desktop
```

## Windows
1. **OBS Studio** (https://obsproject.com): instalarlo basta, no hace falta abrirlo. Aporta el
   dispositivo "OBS Virtual Camera" que usan Zoom, Meet, Teams, etc.
2. **adb** (solo para USB): descarga *SDK Platform-Tools* de Google y pon la carpeta
   `platform-tools` junto al programa (o en el PATH). Algunos teléfonos necesitan el driver USB del fabricante.
3. **Audio** (opcional): instala **VB-Cable** (https://vb-audio.com/Cable/). En el cliente elige
   "Audio a: CABLE Input" y en la app de videollamada usa "CABLE Output" como micrófono.
4. Ejecutar:
   - con Python 3.10+: doble clic en `run.bat`
   - o crear un `.exe`: `build-windows.bat` → `dist\PocketLens-windows-x64.exe`
     (pon la carpeta `platform-tools` junto al .exe para usar USB).

Para Wi-Fi no hace falta adb: elige "Wi-Fi" y escribe la IP que muestra la app.

## Puertos
8554 vídeo H.264 · 8555 audio PCM · 8556 web/API · 8557/UDP detección. Por USB se redirigen con `adb forward`.

## Estructura
- `engine.py`: adb, API del teléfono, cámara/micro virtuales, hilos de vídeo/audio, detección LAN.
- `webcam_client.py`: interfaz (PySide6).
- `make_icons.py`: regenera `assets/icon.{svg,png,ico}`.
