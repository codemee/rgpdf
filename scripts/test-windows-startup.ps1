# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only
param([Parameter(Mandatory)][string]$Binary)
$ErrorActionPreference = 'Stop'
$binaryPath = (Resolve-Path -LiteralPath $Binary).Path
$testRoot = Join-Path $env:RUNNER_TEMP ('rgpdf-startup-' + [guid]::NewGuid().ToString('N'))
if (-not $env:RUNNER_TEMP) { throw 'This smoke test runs only in CI' }
$null = New-Item -ItemType Directory -Path $testRoot
$trace = Join-Path $testRoot 'trace.jsonl'
$env:RGPDF_STARTUP_TRACE = $trace
try {
  $watch = [Diagnostics.Stopwatch]::StartNew()
  $primary = Start-Process -FilePath $binaryPath -PassThru
  do {
    Start-Sleep -Milliseconds 100
    $primary.Refresh()
  } until ($primary.MainWindowHandle -ne 0 -or $primary.HasExited -or $watch.Elapsed.TotalSeconds -ge 30)
  if ($primary.HasExited -or $primary.MainWindowHandle -eq 0 -or -not $primary.Responding) { throw 'Primary window did not start' }
  Write-Host "Primary responsive in $($watch.Elapsed.TotalSeconds.ToString('F2')) seconds"
  $folder = Join-Path $testRoot 'folder with spaces 中文'
  $null = New-Item -ItemType Directory -Path $folder
  $file = Join-Path $folder 'document.txt'
  Set-Content -LiteralPath $file -Value 'No search should start'
  $watch.Restart()
  $secondary = Start-Process -FilePath $binaryPath -ArgumentList ('-- "' + $file + '"') -PassThru
  if (-not $secondary.WaitForExit(10000) -or $secondary.ExitCode -ne 0) { throw 'Forwarding process did not exit successfully' }
  Write-Host "Forwarded file in $($watch.Elapsed.TotalSeconds.ToString('F2')) seconds"
  $deadline = (Get-Date).AddSeconds(5)
  do {
    Start-Sleep -Milliseconds 100
    $received = Get-ItemPropertyValue -LiteralPath 'HKCU:\Software\rgpdf\rgpdf\search' -Name folder -ErrorAction SilentlyContinue
  } until ($received -eq $folder -or (Get-Date) -gt $deadline)
  if ($received -ne $folder) { throw 'Existing window did not open the file parent folder' }
  $forwarded = @(Get-Content -LiteralPath $trace | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object event -eq 'forwarded')
  if ($forwarded.Count -ne 1 -or $forwarded[0].heavy_modules.Count -ne 0) { throw 'Forwarding path imported GUI/PDF modules' }
  if (@(Get-Process -Name rgpdf -ErrorAction SilentlyContinue | Where-Object Path -eq $binaryPath).Count -ne 1) { throw 'Unexpected extra GUI process' }
  Get-Content -LiteralPath $trace
  $null = $primary.CloseMainWindow()
  if (-not $primary.WaitForExit(20000)) { throw 'Primary did not shut down cleanly' }
} finally {
  Remove-Item Env:RGPDF_STARTUP_TRACE -ErrorAction SilentlyContinue
  Get-Process -Name rgpdf -ErrorAction SilentlyContinue |
    Where-Object Path -eq $binaryPath | Stop-Process -Force -ErrorAction SilentlyContinue
}
