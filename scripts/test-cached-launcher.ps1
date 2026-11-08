# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only
$ErrorActionPreference = 'Stop'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $compiler /nologo /codepage:65001 /target:exe /platform:x64 /main:RgPdfBootstrap.CacheTests /out:build-assets\cache-tests.exe `
  /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.Web.Extensions.dll `
  scripts\windows-cached-launcher\Launcher.cs scripts\windows-cached-launcher\CacheTests.cs build-assets\cached-runtime\BundleInfo.g.cs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& build-assets\cache-tests.exe
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
