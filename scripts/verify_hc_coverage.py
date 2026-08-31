#!/usr/bin/env python3
"""External verification for HC-12 aggregate coverage >=80% and HC-13 per-module floors."""

from __future__ import annotations

import io
import json
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


def run_cmd(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO_ROOT,
        env=env,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def check_hc12() -> bool:
    cov_file = REPO_ROOT / "coverage.json"
    if not cov_file.exists():
        print(
            f"{FAIL_SYM}: HC-12 coverage.json not found (run pytest with --cov first)"
        )
        return False
    try:
        with open(cov_file, encoding="utf-8") as f:
            data = json.load(f)
        total_pct = data["totals"]["percent_covered"]
    except Exception as exc:
        print(f"{FAIL_SYM}: HC-12 unable to read coverage.json: {exc}")
        return False
    ok = total_pct >= 80.0
    print(
        f"{PASS_SYM if ok else FAIL_SYM}: HC-12 aggregate coverage {total_pct:.1f}% (>=80%)"
    )
    return ok


def check_hc13() -> bool:
    rc, out, err = run_cmd([PY, "scripts/check_per_module_coverage.py"], timeout=60)
    ok = rc == 0
    print(
        "HC-13 per-module coverage floors (via scripts/check_per_module_coverage.py):"
    )
    for line in (out + err).strip().splitlines():
        if line.strip():
            print(f"  {line}")
    print(
        f"{PASS_SYM if ok else FAIL_SYM}: HC-13 floors {'ALL MET' if ok else 'FAILED'}"
    )
    return ok


def main() -> int:
    print("=" * 70)
    print("HC-12/13 Coverage External Verification")
    print(f"Interpreter: {PY}")
    print("=" * 70)
    results = {"HC-12": check_hc12(), "HC-13": check_hc13()}
    print("=" * 70)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"TOTAL: {passed}/{total} passed")
    if passed == total:
        print("ALL COVERAGE CHECKS PASSED")
        return 0
    print("SOME COVERAGE CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
