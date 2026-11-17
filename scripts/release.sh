#!/usr/bin/env bash
# Publishes a new version: ./scripts/release.sh 2.2.0
#  1. checks CHANGELOG.md has '## [X.Y.Z]', bumps VERSION, commits and pushes
#  2. builds and signs the APK locally (key never leaves this machine)
#  3. creates the GitHub release with the APK and the changelog notes
# GitHub Actions then attaches the Linux and Windows binaries. Installed apps
# (Android and desktop) detect the new release and offer to update.
set -euo pipefail
cd "$(dirname "$0")/.."
V="${1:?uso: scripts/release.sh X.Y.Z}"
REPO="$(cat REPO)"
[[ "$V" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Versión inválida: $V"; exit 1; }
git diff --quiet && git diff --cached --quiet || { echo "Hay cambios sin commitear."; exit 1; }
grep -q "^## \[$V\]" CHANGELOG.md || { echo "Añade una sección '## [$V]' en CHANGELOG.md"; exit 1; }
[ -f "$HOME/.android/pocketlens-release.jks" ] || [ -n "${KEYSTORE:-}" ] || { echo "Falta la clave de firma de release."; exit 1; }

if [ "$(cat VERSION)" != "$V" ]; then
  echo "$V" > VERSION
  git add VERSION
  git commit -m "release: v$V"
fi
git push origin HEAD

./build.sh
mkdir -p build/release
cp WebCam.apk "build/release/PocketLens-$V.apk"
awk -v v="$V" 'index($0, "## [" v "]") == 1 {f=1; next} /^## / {f=0} f' CHANGELOG.md > build/release/notes.md

gh release create "v$V" -R "$REPO" --target "$(git rev-parse HEAD)" \
  --title "PocketLens v$V" --notes-file build/release/notes.md "build/release/PocketLens-$V.apk"
git fetch -q --tags origin
echo "Release v$V creado. Binarios de escritorio: https://github.com/$REPO/actions"
