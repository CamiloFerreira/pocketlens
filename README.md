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
| `PocketLens-linux-x86_64` | Linux (binario único; `chmod +x` y ejecutar) |
| `PocketLens-windows-x64.exe` | Windows 10/11 |

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
client\build-windows.bat    # .exe Windows
```

## Publicar una versión

1. Añade la sección `## [X.Y.Z]` en [CHANGELOG.md](CHANGELOG.md).
2. `./scripts/release.sh X.Y.Z`

El script compila y firma el APK en tu máquina, crea el release con las notas del changelog y
GitHub Actions le añade los binarios de Linux y Windows. Las apps instaladas lo detectan y ofrecen actualizar.

La clave de firma (`~/.android/pocketlens-release.jks` + `.pass`) **solo vive en tu PC**: haz copia de
seguridad. Todas las versiones deben firmarse con la misma clave o Android rechazará la actualización.
