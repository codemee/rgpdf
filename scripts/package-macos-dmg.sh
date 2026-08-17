#!/bin/sh
# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

set -eu
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-.venv/bin/python}"
VERSION="${VERSION:-$("$PYTHON" -c 'from rgpdf import __version__; print(__version__)')}"
ARCH="${ARCH:-$(uname -m)}"
OUTPUT="${1:-dist/rgpdf-$VERSION-macos-$ARCH.dmg}"
APP="dist/rgpdf.app"

if [ ! -d "$APP" ]; then
    printf '%s\n' "Missing $APP; run ./scripts/build-macos.sh first." >&2
    exit 1
fi

staging="$(mktemp -d "${TMPDIR:-/tmp}/rgpdf-dmg.XXXXXX")"
trap 'rm -rf "$staging"' EXIT HUP INT TERM

ditto "$APP" "$staging/rgpdf.app"
ln -s /Applications "$staging/Applications"
mkdir -p "$(dirname "$OUTPUT")"
hdiutil create \
    -volname "rgpdf $VERSION" \
    -srcfolder "$staging" \
    -format UDZO \
    -ov \
    "$OUTPUT"

printf '%s\n' "Built $OUTPUT"
