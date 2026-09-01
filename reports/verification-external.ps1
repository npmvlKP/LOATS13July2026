# LOATS13July2026 - External Python Verification Script (PowerShell)
# Run from repo root:  .\reports\verification-external.ps1
# This script re-executes the gates that were used to close the acceptance matrix.

$ErrorActionPreference = 'Stop'
$REPO = Resolve-Path (Join-Path $PSScriptRoot '..')
$PY = Join-Path $REPO 'loatsNEW\Scripts\python.exe'

New-Item -ItemType Directory -Force -Path (Join-Path $REPO 'reports\security') | Out-Null

function Invoke-Step($Name, $Arguments) {
    Write-Host "=== $Name ===" -ForegroundColor Cyan
    & $PY @Arguments
    if ($LASTEXITCODE -ne 0) { throw "FAILED: $Name (exit $LASTEXITCODE)" }
    Write-Host "OK: $Name`n" -ForegroundColor Green
}

Set-Location $REPO

Invoke-Step 'HC-01..HC-13 structural/quality delegate (verify_hc_all.py)' @('scripts\verify_hc_all.py')
Invoke-Step 'HC-01..HC-27 full registry (health-final-20260901.json)' @('scripts\verify_hc_registry.py', '--json', 'reports\health\health-final-20260901.json')
Invoke-Step 'TODO-8 / HC-15 external 4th producer / ADR verification' @('scripts\verify_todo8_external.py')
Invoke-Step 'Pytest full suite (coverage >=80%)' @('-m', 'pytest', 'tests\', '--cov=src', '--cov-fail-under=80', '--cov-report=json', '-q')
Invoke-Step 'Ruff lint' @('-m', 'ruff', 'check', 'src\', 'tests\', 'scripts\', '--config', 'pyproject.toml')
Invoke-Step 'Ruff format check' @('-m', 'ruff', 'format', 'src\', 'tests\', 'scripts\', '--config', 'pyproject.toml', '--check')
Invoke-Step 'mypy --strict' @('-m', 'mypy', 'src\', '--strict', '--config-file', 'pyproject.toml')
Invoke-Step 'Bandit security scan' @('-m', 'bandit', '-r', 'src\', '-f', 'json', '-o', 'reports\security\bandit-20260901.json')
Invoke-Step 'pip-audit dependency scan' @('-m', 'pip_audit', '--format=json', '--desc', '-o', 'reports\security\pip-audit-20260901.json')

Write-Host 'ALL EXTERNAL VERIFICATION STEPS PASSED' -ForegroundColor Green
