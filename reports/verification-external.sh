#!/usr/bin/env bash
# LOATS13July2026 - External Python Verification Script (Bash/Git-Bash)
# Run from repo root:  ./reports/verification-external.sh
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="$REPO/loatsNEW/Scripts/python.exe"

cd "$REPO"

mkdir -p reports/security

run() {
  local name="$1"
  shift
  echo "=== $name ==="
  "$PY" "$@"
  echo "OK: $name"
  echo
}

run 'HC-01..HC-13 structural/quality delegate' scripts/verify_hc_all.py
run 'HC-01..HC-27 full registry (health-final-20260901.json)' scripts/verify_hc_registry.py --json reports/health/health-final-20260901.json
run 'TODO-8 / HC-15 external 4th producer / ADR verification' scripts/verify_todo8_external.py
run 'Pytest full suite (coverage >=80%)' -m pytest tests/ --cov=src --cov-fail-under=80 --cov-report=json -q
run 'Ruff lint' -m ruff check src/ tests/ scripts/ --config pyproject.toml
run 'Ruff format check' -m ruff format src/ tests/ scripts/ --config pyproject.toml --check
run 'mypy --strict' -m mypy src/ --strict --config-file pyproject.toml
run 'Bandit security scan' -m bandit -r src/ -f json -o reports/security/bandit-20260901.json
run 'pip-audit dependency scan' -m pip_audit --format=json --desc -o reports/security/pip-audit-20260901.json

echo 'ALL EXTERNAL VERIFICATION STEPS PASSED'
