#!/usr/bin/env python3
"""Verify structural cleanup: removal of empty package shells and preservation of single-file modules."""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

# Windows UTF-8 fix so subprocess/piped output does not crash on box symbols.
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
    """Return project venv interpreter when available, else sys.executable."""
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


def check_empty_shells_removed() -> bool:
    """Verify empty package shells (strength/, trading_strategy/) were removed."""
    empty_shells = [
        REPO_ROOT / "src" / "loats" / "strength",
        REPO_ROOT / "src" / "loats" / "trading_strategy",
    ]
    all_ok = True
    print("Empty Package Shell Check:")
    for shell in empty_shells:
        exists = shell.is_dir()
        ok = not exists
        print(
            f"  {PASS_SYM if ok else FAIL_SYM}: {shell.name} {'exists (should be removed)' if exists else 'removed'}"
        )
        all_ok = all_ok and ok
    return all_ok


def check_single_file_modules_exist() -> bool:
    """Verify single-file modules (strength.py) still exist."""
    single_files = [REPO_ROOT / "src" / "loats" / "strength.py"]
    all_ok = True
    print("\nSingle-File Module Check:")
    for f in single_files:
        exists = f.is_file()
        print(
            f"  {PASS_SYM if exists else FAIL_SYM}: {f.name} {'exists' if exists else 'missing'}"
        )
        all_ok = all_ok and exists
    return all_ok


def check_imports_work() -> bool:
    """Verify imports still work after cleanup."""
    code = (
        "import sys; sys.path.insert(0, 'src'); "
        "from loats.strength import StrengthEngine, StrengthSource; "
        "from loats.rules import CMPRulesEngine; "
        "from loats.sizing import SizingEngine; "
        "print('imports ok')"
    )
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("OPENALGO_API_KEY", "verify-structural-key")
    env.setdefault("OPENALGO_BASE_URL", "http://127.0.0.1:5000")
    env.setdefault("OPENALGO_MODE", "ANALYZE")

    result = subprocess.run(
        [PY, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO_ROOT,
        env=env,
    )
    ok = "imports ok" in result.stdout
    print(
        f"\nImport Check:\n  {PASS_SYM if ok else FAIL_SYM}: from loats.strength import StrengthEngine, StrengthSource"
    )
    if not ok:
        print(f"  stdout: {result.stdout.strip()}")
        print(f"  stderr: {result.stderr.strip()}")
    return ok


def main() -> int:
    print("=" * 70)
    print("STRUCTURAL CLEANUP VERIFICATION")
    print(f"Interpreter: {PY}")
    print("=" * 70)

    results = {
        "empty_shells_removed": check_empty_shells_removed(),
        "single_files_exist": check_single_file_modules_exist(),
        "imports_work": check_imports_work(),
    }

    print("=" * 70)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"TOTAL: {passed}/{total} checks passed")
    if passed == total:
        print("STRUCTURAL CLEANUP VERIFICATION PASSED")
        return 0
    print("STRUCTURAL CLEANUP VERIFICATION FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
