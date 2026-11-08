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

$version = & $Python -c 'from rgpdf import __version__; print(__version__)'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$filename = "rgpdf-$version-windows-x86_64.zip"
Compress-Archive -LiteralPath dist\rgpdf -DestinationPath "dist\$filename" -Force
$hash = (Get-FileHash "dist\$filename" -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $filename" | Set-Content "dist\$filename.sha256" -Encoding ascii
Write-Host "Built dist\$filename; extract and run rgpdf\rgpdf.exe"
