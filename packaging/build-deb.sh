#!/usr/bin/env bash
# Builds pocketlens_<version>_amd64.deb from the PyInstaller Linux binary.
#   packaging/build-deb.sh [--binary PATH] [--apk PATH] [--out DIR]
# Defaults: client/dist/PocketLens-linux-x86_64 (built if missing), ./WebCam.apk, ./dist
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/client/dist/PocketLens-linux-x86_64"
APK="$ROOT/WebCam.apk"
OUT="$ROOT/dist"
while [ $# -gt 0 ]; do
  case "$1" in
    --binary) BIN="$2"; shift ;;
    --apk) APK="$2"; shift ;;
    --out) OUT="$2"; shift ;;
    *) echo "opción desconocida: $1"; exit 1 ;;
  esac
  shift
done
VERSION="$(tr -d ' \n\r' < "$ROOT/VERSION")"
[ -f "$BIN" ] || "$ROOT/client/build-linux.sh"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
P="$STAGE/pocketlens"
install -d "$P/DEBIAN" "$P/opt/pocketlens" "$P/usr/bin" "$P/usr/share/applications" \
  "$P/usr/share/icons/hicolor/256x256/apps" "$P/usr/share/icons/hicolor/scalable/apps" \
  "$P/usr/share/doc/pocketlens" "$P/etc/modprobe.d" "$P/etc/modules-load.d"

install -m 0755 "$BIN" "$P/opt/pocketlens/PocketLens"
install -m 0755 "$ROOT/webcam.sh" "$P/opt/pocketlens/webcam.sh"
[ -f "$APK" ] && install -m 0644 "$APK" "$P/opt/pocketlens/WebCam.apk"
ln -s /opt/pocketlens/PocketLens "$P/usr/bin/pocketlens"
cat > "$P/usr/bin/pocketlens-cli" <<'SH'
#!/bin/sh
exec /opt/pocketlens/webcam.sh "$@"
SH
chmod 0755 "$P/usr/bin/pocketlens-cli"
install -m 0644 "$ROOT/client/assets/icon.png" "$P/usr/share/icons/hicolor/256x256/apps/pocketlens.png"
install -m 0644 "$ROOT/client/assets/icon.svg" "$P/usr/share/icons/hicolor/scalable/apps/pocketlens.svg"
install -m 0644 "$ROOT/packaging/deb/pocketlens.desktop" "$P/usr/share/applications/pocketlens.desktop"
install -m 0644 "$ROOT/packaging/deb/modprobe.conf" "$P/etc/modprobe.d/pocketlens.conf"
install -m 0644 "$ROOT/packaging/deb/modules-load.conf" "$P/etc/modules-load.d/pocketlens.conf"
gzip -9n -c "$ROOT/CHANGELOG.md" > "$P/usr/share/doc/pocketlens/changelog.gz"
chmod 0644 "$P/usr/share/doc/pocketlens/changelog.gz"
install -m 0644 "$ROOT/packaging/deb/copyright" "$P/usr/share/doc/pocketlens/copyright"

SIZE_KB=$(du -sk --exclude=DEBIAN "$P" | cut -f1)
sed -e "s/@VERSION@/$VERSION/" -e "s/@SIZE@/$SIZE_KB/" "$ROOT/packaging/deb/control" > "$P/DEBIAN/control"
install -m 0755 "$ROOT/packaging/deb/postinst" "$P/DEBIAN/postinst"
install -m 0755 "$ROOT/packaging/deb/postrm" "$P/DEBIAN/postrm"
printf '/etc/modprobe.d/pocketlens.conf\n/etc/modules-load.d/pocketlens.conf\n' > "$P/DEBIAN/conffiles"

mkdir -p "$OUT"
DEB="$OUT/pocketlens_${VERSION}_amd64.deb"
dpkg-deb --root-owner-group -Zxz --build "$P" "$DEB" >/dev/null
echo "OK -> $DEB"
