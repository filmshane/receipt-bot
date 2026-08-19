#!/usr/bin/env pwsh
#Requires -Version 5.1
<#
.SYNOPSIS
  Setup Telegram Receipt Analysis Assistant (Windows).

.DESCRIPTION
  Creates .venv, installs package editable + dev deps, copies .env.example.
  Cross-platform twin: scripts/setup.sh (Ubuntu 24.04 /usr/bin/python3).
#>
[CmdletBinding()]
param(
    [switch]$Dev = $true
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "pyproject.toml"))) {
    $Root = $PSScriptRoot
    if (-not (Test-Path (Join-Path $Root "pyproject.toml"))) {
        throw "Cannot find project root (pyproject.toml)."
    }
}
Set-Location $Root
Write-Host "Project root: $Root"

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) { throw "Python not found on PATH. Install Python 3.10+." }

$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "Creating .venv ..."
    & $py.Source -m venv (Join-Path $Root ".venv")
}
if (-not (Test-Path $venvPy)) { throw "venv python missing: $venvPy" }

Write-Host "Upgrading pip / installing package ..."
& $venvPy -m pip install --upgrade pip wheel setuptools
if ($Dev) {
    & $venvPy -m pip install -e ".[dev]"
} else {
    & $venvPy -m pip install -e .
}

$envExample = Join-Path $Root ".env.example"
$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Write-Host "Created .env from .env.example — edit secrets before run."
    }
} else {
    Write-Host ".env already exists (left unchanged)."
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root "data") | Out-Null
Write-Host ""
Write-Host "Setup OK. Next:"
Write-Host "  1. Edit .env (TELEGRAM_BOT_TOKEN, XAI_API_KEY, SMTP_PASSWORD, CFO_EMAIL)"
Write-Host "  2. .\scripts\run.ps1"
Write-Host "  3. .\scripts\test.ps1"
