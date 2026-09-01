#!/usr/bin/env python3
"""LOATS13July2026 - External Python verification entry point.

Re-executes the gates that closed the acceptance matrix.  Run from the repo root
with the project venv:

    loatsNEW\\Scripts\\python.exe reports\\verification-external.py

This script is deliberately self-contained, uses only the project venv, and
avoids shell quoting by passing every command as a list (shell=False).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PY = str(REPO_ROOT / "loatsNEW" / "Scripts" / "python.exe")

REPORT_BANDIT = str(REPO_ROOT / "reports" / "security" / "bandit-20260901.json")
REPORT_PIP_AUDIT = str(REPO_ROOT / "reports" / "security" / "pip-audit-20260901.json")
HEALTH_JSON = str(REPO_ROOT / "reports" / "health" / "health-final-20260901.json")

STEPS: list[tuple[str, list[str]]] = [
    (
        "HC-01..HC-13 structural/quality delegate",
        [PY, str(REPO_ROOT / "scripts" / "verify_hc_all.py")],
    ),
    (
        "HC-01..HC-27 full registry (rewrite health-final-20260901.json)",
        [
            PY,
            str(REPO_ROOT / "scripts" / "verify_hc_registry.py"),
            "--json",
            HEALTH_JSON,
        ],
    ),
    (
        "TODO-8 / HC-15 external 4th producer / ADR verification",
        [PY, str(REPO_ROOT / "scripts" / "verify_todo8_external.py")],
    ),
    (
        "Pytest full suite (1170 tests, coverage >=80%)",
        [
            PY,
            "-m",
            "pytest",
            "tests/",
            "--cov=src",
            "--cov-fail-under=80",
            "--cov-report=json",
            "-q",
        ],
    ),
    (
        "Ruff lint",
        [
            PY,
            "-m",
            "ruff",
            "check",
            "src/",
            "tests/",
            "scripts/",
            "--config",
            str(REPO_ROOT / "pyproject.toml"),
        ],
    ),
    (
        "Ruff format check",
        [
            PY,
            "-m",
            "ruff",
            "format",
            "src/",
            "tests/",
            "scripts/",
            "--config",
            str(REPO_ROOT / "pyproject.toml"),
            "--check",
        ],
    ),
    (
        "mypy --strict",
        [
            PY,
            "-m",
            "mypy",
            "src/",
            "--strict",
            "--config-file",
            str(REPO_ROOT / "pyproject.toml"),
        ],
    ),
    (
        "Bandit security scan",
        [
            PY,
            "-m",
            "bandit",
            "-r",
            "src/",
            "-f",
            "json",
            "-o",
            REPORT_BANDIT,
        ],
    ),
    (
        "pip-audit dependency scan",
        [
            PY,
            "-m",
            "pip_audit",
            "--format=json",
            "--desc",
            "-o",
            REPORT_PIP_AUDIT,
        ],
    ),
]


def _run(name: str, cmd: list[str]) -> bool:
    print(f"=== {name} ===")
    try:
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            shell=False,
            check=False,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as e:
        print(f"EXCEPTION: {e}")
        return False
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if result.returncode != 0:
        print(f"FAILED: {name} (exit {result.returncode})")
        return False
    print(f"OK: {name}\n")
    return True


def main() -> int:
    if not Path(PY).exists():
        print(f"Project venv python not found at {PY}")
        return 1
    passed = 0
    for name, cmd in STEPS:
        if _run(name, cmd):
            passed += 1
        else:
            break
    print(f"RESULT: {passed}/{len(STEPS)} steps passed")
    return 0 if passed == len(STEPS) else 1


if __name__ == "__main__":
    sys.exit(main())
