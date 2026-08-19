#!/usr/bin/env pwsh
#Requires -Version 5.1
<#
.SYNOPSIS
  Run Telegram Receipt Analysis Assistant (Windows long-polling).

.DESCRIPTION
  Uses project .venv. Twin script: scripts/run.sh for Ubuntu 24.04.
#>
[CmdletBinding()]
param(
    [switch]$SetupIfMissing
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "pyproject.toml"))) {
    throw "Project root not found from scripts/."
}
Set-Location $Root

$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    if ($SetupIfMissing) {
        & (Join-Path $PSScriptRoot "setup.ps1")
    } else {
        throw "Missing .venv. Run: .\scripts\setup.ps1"
    }
}

$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
    throw "Missing .env — copy .env.example to .env and fill secrets."
}

Write-Host "Starting receipt-bot (Ctrl+C to stop) ..."
& $venvPy -m receipt_bot @args
exit $LASTEXITCODE
