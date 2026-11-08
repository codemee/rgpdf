# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

param(
    [string]$Python = ".venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

& $Python scripts\generate_windows_icon.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python -m PyInstaller --noconfirm --clean rgpdf.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Built dist\rgpdf.exe"
