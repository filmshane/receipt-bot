#!/usr/bin/env pwsh
#Requires -Version 5.1
<#
.SYNOPSIS
  Run pytest for receipt-bot (Windows).
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    throw "Missing .venv. Run: .\scripts\setup.ps1"
}

& $venvPy -m pytest -q @args
exit $LASTEXITCODE
