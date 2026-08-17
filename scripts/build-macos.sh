#!/bin/sh
# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

set -eu
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-.venv/bin/python}"

"$PYTHON" scripts/generate_macos_icon.py
"$PYTHON" -m PyInstaller --noconfirm --clean rgpdf-macos.spec
printf '%s\n' "Built dist/rgpdf.app"
