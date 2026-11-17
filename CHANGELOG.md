# Changelog

## [2.1.0] - 2026-11-17

Primera versión pública de **PocketLens**.

### Android
- Vista previa a pantalla completa con barra de estado (EN VIVO, cámara, resolución, fps, Mbps).
- Controles: cambiar cámara, linterna, silenciar micrófono, pantalla apagada, ajustes.
- Gestos: tocar para enfocar (con exposición), pellizcar para zoom, zoom rápido 1×/2×/5×, doble toque oculta controles.
- Vídeo H.264 por hardware (puerto 8554), micrófono (8555), visor web MJPEG + API (8556), detección en red (UDP 8557).
- Actualización automática desde GitHub Releases.

### Escritorio (Linux y Windows)
- Cliente con vista previa, detección automática del teléfono (USB y Wi-Fi) y controles remotos.
- Linux: cámara virtual v4l2loopback y micrófono PipeWire «Android Mic».
- Windows: OBS Virtual Camera y audio vía VB-Cable.
- Se actualiza solo y actualiza la app del teléfono por USB.
