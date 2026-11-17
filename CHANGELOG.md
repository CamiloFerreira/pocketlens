# Changelog

## [2.2.0] - 2026-11-17

### Escritorio
- **Efectos de fondo** al estilo Teams/Meet, con detección de personas por IA que corre en el PC (MediaPipe):
  - Galería de fondos: desenfoque, 8 fondos incluidos (Estudio, Ventanal, Atardecer, Bokeh, Aurora, Océano,
    Grafito, PocketLens) y tus propias imágenes (botón «+»; clic derecho para quitarlas).
  - Intensidad del desenfoque ajustable (1–100 %).
  - Precisión «Alta»: segunda pasada ampliada sobre la persona, descarta objetos sueltos y ajusta los bordes
    a la imagen real (guided filter). «Rápida» para PCs modestos.
  - La segmentación corre en un hilo aparte: 30 fps a 1080p.
  - Se activa o desactiva al vuelo desde la tarjeta «Fondo» o el botón de la barra flotante; la vista previa
    indica si hay una persona en cuadro. Funciona en cualquier app de videollamadas vía la cámara virtual.
  - Para usar tu imagen: botón «Usar mi imagen como fondo…», arrastrarla a la ventana o el menú de fondos
    de la barra flotante.
- El **micrófono** se puede apagar y encender mientras estás conectado (antes había que desconectar).
- Corregido: los interruptores (Espejo, Micrófono, Efecto) cambiaban el estado pero no su dibujo.
- La tarjeta «Fondo» va arriba, junto a «Dispositivo».

### Linux
- Si el cliente se cierra de golpe, la cámara virtual ya no queda bloqueada («is not a video output
  device») y el micrófono virtual «Android Mic» desaparece junto con la app.
- Corregido: el cliente instalado (.deb / binario) no detectaba el teléfono por USB. El `adb` del
  sistema heredaba las librerías empaquetadas del binario y no arrancaba (`GLIBCXX_3.4.31 not found`).

## [2.1.1] - 2026-11-17

### Linux
- Nuevo paquete **.deb** (`pocketlens_2.1.1_amd64.deb`): instala el cliente en el menú de aplicaciones,
  los comandos `pocketlens` y `pocketlens-cli`, y deja configurada la cámara virtual «Android Cam»
  para que se cargue al arrancar (ya no pide contraseña al conectar).
- Las instalaciones desde .deb se actualizan descargando el nuevo paquete (pide contraseña una vez).

### Seguridad
- **Actualizaciones obligatorias**: un release puede fijar una versión mínima soportada
  (`./scripts/release.sh X.Y.Z --mandatory`). Las versiones anteriores quedan bloqueadas:
  la app Android desactiva cámara y micrófono y solo permite actualizar o salir; el cliente
  de escritorio no conecta y exige actualizar también la app del teléfono.

### Escritorio
- Corregido: el interruptor «Espejo» (y «Micrófono») saltaba a la esquina de la tarjeta al pulsarlo.

### Android
- Las notas de la actualización se muestran como texto limpio.
- La comprobación de actualizaciones ignora cachés.

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
