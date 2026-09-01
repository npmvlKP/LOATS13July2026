#!/usr/bin/env python3
"""External build-success verification for LOATS13July2026.

Re-runs the two canonical gate suites the user requested:

1. HC Registry verifier (HC-01..HC-27) — must report 27 PASS.
2. FR7 health-check master (28 checks) — must report zero FAIL.

Usage:

    python scripts/verify_build_success.py

Exit code:

    0 if both suites pass, 1 otherwise.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _resolve_python() -> str:
    """Prefer the project venv, fall back to the running interpreter."""
    candidates = [
        REPO_ROOT / "loatsNEW" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
    ]
    for cand in candidates:
        if cand.exists():
            return str(cand)
    return sys.executable


PY = _resolve_python()


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("OPENALGO_API_KEY", "verify-build-success-key")
    env.setdefault("OPENALGO_BASE_URL", "http://127.0.0.1:5000")
    env.setdefault("OPENALGO_MODE", "ANALYZE")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    return env


def _run(cmd: list[str], timeout: int) -> tuple[int, str]:
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO_ROOT,
        env=_child_env(),
        timeout=timeout,
    )
    return result.returncode, result.stdout + result.stderr


def _registry_passes() -> bool:
    print("\n[1/2] Running HC Registry verifier (HC-01..HC-27) ...")
    rc, out = _run([PY, str(REPO_ROOT / "scripts" / "verify_hc_registry.py")], timeout=300)
    tail = "\n".join(out.splitlines()[-5:])
    print(tail)
    return rc == 0 and "PASS=27 FAIL=0" in out


def _health_check_passes() -> bool:
    print("\n[2/2] Running FR7 health-check master ...")
    rc, out = _run([PY, str(REPO_ROOT / "scripts" / "fr7_health_check.py")], timeout=600)
    tail = "\n".join(out.splitlines()[-10:])
    print(tail)
    return rc == 0 and "FAIL:   0" in out


def main() -> int:
    print("=" * 70)
    print("LOATS13July2026 Build-Success Verification")
    print(f"Interpreter: {PY}")
    print("=" * 70)

    registry_ok = _registry_passes()
    health_ok = _health_check_passes()

    print("\n" + "=" * 70)
    if registry_ok and health_ok:
        print("[PASS] All gate suites green. Build verified.")
        return 0
    print("[FAIL] One or more gate suites failed.")
    if not registry_ok:
        print("  - HC Registry verifier failed")
    if not health_ok:
        print("  - FR7 health-check failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
