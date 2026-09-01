#!/usr/bin/env python3
"""LOATS13July2026 - External Python verification entry point.

Re-executes the gates that closed the acceptance matrix.  Run from the repo root
with the project venv:

    loatsNEW\\Scripts\\python.exe reports\\verification-external.py

This script is deliberately self-contained, uses only the project venv, and
avoids shell quoting by passing every command as a list (shell=False).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _resolve_python() -> str:
    """Prefer the project venv interpreter, fall back to sys.executable."""
    candidates = [
        REPO_ROOT / "loatsNEW" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
        REPO_ROOT / "venv" / "Scripts" / "python.exe",
    ]
    for cand in candidates:
        if cand.exists():
            return str(cand)
    return sys.executable


PY = _resolve_python()
REPORT_BANDIT = str(REPO_ROOT / "reports" / "security" / "bandit-20260901.json")
REPORT_PIP_AUDIT = str(REPO_ROOT / "reports" / "security" / "pip-audit-20260901.json")
HEALTH_JSON = str(REPO_ROOT / "reports" / "health" / "health-final-20260901.json")

# Ensure reports/security exists for JSON outputs.
Path(REPORT_BANDIT).parent.mkdir(parents=True, exist_ok=True)

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
        "Pytest full suite (coverage >=80%)",
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


def _safe_print(text: str) -> None:
    """Write to stdout; fall back to ASCII if Windows encoding breaks."""
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.write(text.encode("ascii", "replace").decode("ascii") + "\n")
        sys.stdout.flush()


def _run(name: str, cmd: list[str]) -> bool:
    _safe_print(f"=== {name} ===")
    start = time.perf_counter()
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
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except Exception as e:
        _safe_print(f"EXCEPTION: {e}")
        return False
    if result.stdout:
        _safe_print(result.stdout.rstrip())
    if result.stderr:
        _safe_print(result.stderr.rstrip())
    elapsed = time.perf_counter() - start
    if result.returncode != 0:
        _safe_print(f"FAILED: {name} (exit {result.returncode}, {elapsed:.1f}s)")
        return False
    _safe_print(f"OK: {name} ({elapsed:.1f}s)\n")
    return True


def main() -> int:
    if not Path(PY).exists():
        _safe_print(f"Project venv python not found at {PY}")
        return 1
    passed = 0
    for name, cmd in STEPS:
        if _run(name, cmd):
            passed += 1
        else:
            break
    _safe_print(f"RESULT: {passed}/{len(STEPS)} steps passed")
    return 0 if passed == len(STEPS) else 1


if __name__ == "__main__":
    sys.exit(main())
