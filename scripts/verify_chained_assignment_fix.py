#!/usr/bin/env python3
"""External verification for pandas chained-assignment fix (rules.py ADX calculation)."""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "buffer") and not isinstance(
            sys.stdout, io.TextIOWrapper
        ):
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer,
                encoding="utf-8",
                errors="replace",
                line_buffering=True,
            )
        if hasattr(sys.stderr, "buffer") and not isinstance(
            sys.stderr, io.TextIOWrapper
        ):
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer,
                encoding="utf-8",
                errors="replace",
                line_buffering=True,
            )
    except (OSError, ValueError, AttributeError):
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        os.environ.setdefault("PYTHONUTF8", "1")

REPO_ROOT = Path(__file__).resolve().parent.parent
PASS_SYM = "[PASS]"
FAIL_SYM = "[FAIL]"


def _resolve_python() -> str:
    candidates = [
        REPO_ROOT / "loatsNEW" / "Scripts" / "python.exe",
        REPO_ROOT / "loatsNEW" / "bin" / "python",
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "bin" / "python",
    ]
    for cand in candidates:
        if cand.exists():
            return str(cand)
    return sys.executable


PY = _resolve_python()


def check_no_chained_assignment() -> bool:
    """Ensure no pandas chained-assignment warnings in rules.py during tests."""
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    result = subprocess.run(
        [PY, "-m", "pytest", "tests/test_rules_engine.py", "-v", "--tb=no"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO_ROOT,
        env=env,
        timeout=120,
    )
    combined = result.stdout + result.stderr
    warning_markers = (
        "ChainedAssignmentError",
        "SettingWithCopyWarning",
        "chained assignment",
    )
    found = [m for m in warning_markers if m in combined]
    ok = not found
    print(
        f"{PASS_SYM if ok else FAIL_SYM}: No pandas chained-assignment warnings in rules.py tests"
    )
    if found:
        print("  warnings found:")
        for m in found:
            print(f"    - {m}")
    return ok


def main() -> int:
    print("=" * 70)
    print("Pandas Chained-Assignment Fix Verification")
    print(f"Interpreter: {PY}")
    print("=" * 70)
    ok = check_no_chained_assignment()
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
