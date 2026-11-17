<p align="center">
  <img src="client/assets/icon.png" width="96" alt="PocketLens">
</p>

<h1 align="center">PocketLens</h1>
<p align="center"><b>Tu teléfono Android como webcam y micrófono para Linux y Windows</b><br>
USB o Wi-Fi · H.264 por hardware · baja latencia · se actualiza solo</p>

---

## Descargas

Última versión en **[Releases](../../releases/latest)**:

| Archivo | Para |
|---|---|
| `PocketLens-X.Y.Z.apk` | Teléfono Android 7.0+ |
| `pocketlens_X.Y.Z_amd64.deb` | Ubuntu / Debian (recomendado en Linux) |
| `PocketLens-linux-x86_64` | Otras distros Linux (binario único; `chmod +x` y ejecutar) |
| `PocketLens-windows-x64.exe` | Windows 10/11 |

Instalar en Ubuntu/Debian:
```bash
sudo apt install ./pocketlens_X.Y.Z_amd64.deb
```
Queda en el menú como **PocketLens** (o `pocketlens` en la terminal; `pocketlens-cli` sin interfaz) y la cámara
virtual «Android Cam» se carga sola al arrancar.

Las apps buscan nuevas versiones solas:
- **Android:** aviso «Actualizar a vX» en la barra superior (o *Ajustes → Buscar actualizaciones*). Descarga e instala; Android pide confirmar.
- **Escritorio:** botón «Actualizar a vX» en la cabecera; se reemplaza y reinicia. Si el teléfono está por USB y tiene una app más vieja, ofrece actualizarla también.

## Cómo funciona

```
 Teléfono (app PocketLens)                       PC (cliente PocketLens)
 Camera2 ─► encoder H.264 ─► TCP 8554 ──USB/WiFi──► decodifica ─► cámara virtual
 Micrófono ─────────────────► TCP 8555 ───────────► micrófono virtual
 Visor web + API ────────────► HTTP 8556            (v4l2loopback / OBS Virtual Camera)
 Anuncio en la red ──────────► UDP 8557 ──────────► detección automática
```

Por USB se usa `adb forward`; por Wi-Fi el cliente encuentra el teléfono solo.

## Android (`android/`)

- Vista previa a pantalla completa, estado EN VIVO, resolución/fps/Mbps y clientes conectados.
- Cambiar cámara, linterna, silenciar micrófono, pantalla apagada (sigue transmitiendo), ajustes.
- Tocar = enfocar (+ exposición) · pellizcar = zoom · 1×/2×/5× · doble toque = ocultar controles.
- La cámara solo se enciende cuando alguien la usa.
- Visor web en `http://IP:8556` desde cualquier navegador (otro móvil, tablet, PC).

API: `/api/status`, `/api/switch`, `/api/torch`, `/api/mic`, `/api/zoom?v=2`, `/api/exposure?v=-3`,
`/api/focus?x=0.5&y=0.5`, `/api/config?res=1280x720&fps=30&bitrate=6&camera=back&audio=1`, `/video`, `/snapshot.jpg`.

## Escritorio (`client/`)

| | Vídeo | Audio |
|---|---|---|
| Linux | v4l2loopback (`/dev/video10`, «Android Cam») | PipeWire, fuente «Android Mic» |
| Windows | «OBS Virtual Camera» (instalar OBS Studio) | VB-Cable («CABLE Output» como micro) |

**Efectos de fondo** (como Teams/Meet): desenfoque con intensidad ajustable, fondos incluidos o tus propias
imágenes, con detección de personas por IA en el PC (MediaPipe, sin enviar nada a internet). Se activa/desactiva
en vivo desde la tarjeta «Fondo» o el botón de la barra flotante, y llega a cualquier app a través de la cámara virtual.

Detalles en [client/README.md](client/README.md).

### Linux sin interfaz (`webcam.sh`)
```bash
./webcam.sh                      # USB, cámara trasera 720p30
./webcam.sh -c front -r 1920x1080 --bitrate 10
./webcam.sh --wifi 192.168.1.50 --preview
```
Requisitos: `adb`, `ffmpeg`, `v4l2-utils`, `python3`, `v4l2loopback-dkms`, PipeWire.

> **v4l2loopback 0.12.7 (Ubuntu):** tras cerrar un escritor que usa `write()` el dispositivo deja de
> anunciar «Video Output». Cliente y script lo reparan sin sudo (`VIDIOC_STREAMON` OUTPUT ficticio).

## Compilar

```bash
./build.sh                  # APK sin Gradle (Android SDK build-tools + JDK)
client/run.sh               # cliente desde el código (crea .venv)
client/build-linux.sh       # binario Linux
packaging/build-deb.sh      # paquete .deb (usa el binario anterior)
client\build-windows.bat    # .exe Windows
```

## Publicar una versión

1. Añade la sección `## [X.Y.Z]` en [CHANGELOG.md](CHANGELOG.md).
2. `./scripts/release.sh X.Y.Z` — o `./scripts/release.sh X.Y.Z --mandatory` si corrige una vulnerabilidad.

**Actualizaciones obligatorias:** con `--mandatory`, X.Y.Z pasa a ser la versión mínima soportada
(`MIN_VERSION`, publicada en las notas de cada release como `<!-- min-version: X.Y.Z -->`).
Cualquier versión anterior:
- **Android:** desactiva cámara y micrófono y muestra un diálogo que no se puede cerrar (Actualizar / Salir).
  El bloqueo se recuerda aunque el teléfono quede sin internet.
- **Escritorio:** no permite conectar hasta actualizar, y se niega a usar un teléfono con app por debajo
  del mínimo (ofrece actualizarla por USB).

El script compila y firma el APK en tu máquina, crea el release con las notas del changelog y
GitHub Actions le añade los binarios de Linux y Windows. Las apps instaladas lo detectan y ofrecen actualizar.

La clave de firma (`~/.android/pocketlens-release.jks` + `.pass`) **solo vive en tu PC**: haz copia de
seguridad. Todas las versiones deben firmarse con la misma clave o Android rechazará la actualización.
