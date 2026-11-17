#!/usr/bin/env bash
# Publishes a new version: ./scripts/release.sh 2.2.0
# Bumps VERSION, checks CHANGELOG has a section for it, commits, tags and pushes.
# GitHub Actions then builds the APK (signed), Linux and Windows binaries and creates the release;
# installed apps (Android & desktop) offer the update automatically.
set -euo pipefail
cd "$(dirname "$0")/.."
V="${1:?uso: scripts/release.sh X.Y.Z}"
[[ "$V" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Versión inválida: $V"; exit 1; }
git diff --quiet && git diff --cached --quiet || { echo "Hay cambios sin commitear."; exit 1; }
grep -q "^## \[$V\]" CHANGELOG.md || { echo "Añade una sección '## [$V]' en CHANGELOG.md"; exit 1; }
echo "$V" > VERSION
git add VERSION CHANGELOG.md
git commit -m "release: v$V"
git tag -a "v$V" -m "PocketLens v$V"
git push origin HEAD "v$V"
echo "Publicado v$V → https://github.com/$(cat REPO)/actions"
