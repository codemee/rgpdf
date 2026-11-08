# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only
param([string]$Python = '.venv\Scripts\python.exe')
$ErrorActionPreference = 'Stop'
& $Python scripts\generate_windows_icon.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$previousMode = $env:RGPDF_BUILD_CACHE_PAYLOAD
try {
  $env:RGPDF_BUILD_CACHE_PAYLOAD = '1'
  & $Python -m PyInstaller --noconfirm --clean rgpdf.spec
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally { $env:RGPDF_BUILD_CACHE_PAYLOAD = $previousMode }
& $Python scripts\package_cached_runtime.py dist\rgpdf-runtime build-assets\cached-runtime
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Windows .NET Framework compiler unavailable' }
& $compiler /nologo /codepage:65001 /target:winexe /platform:x64 /optimize+ /out:dist\rgpdf-cached.exe /win32icon:build-assets\rgpdf.ico `
  /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.Web.Extensions.dll `
  /resource:build-assets\cached-runtime\runtime.zip,rgpdf.runtime.zip `
  /resource:build-assets\cached-runtime\runtime.json,rgpdf.runtime.json `
  scripts\windows-cached-launcher\Launcher.cs build-assets\cached-runtime\BundleInfo.g.cs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$hash = (Get-FileHash -LiteralPath dist\rgpdf-cached.exe -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  rgpdf-cached.exe" | Set-Content dist\rgpdf-cached.exe.sha256 -Encoding ascii
Write-Host 'Built experimental single-file cached launcher: dist\rgpdf-cached.exe'
