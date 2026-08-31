#!/usr/bin/env python3
"""External verification for HC-01/02/03 (structural) + HC-05/06/07/08/09/10 (gates)."""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

# Windows UTF-8 safety so the script does not crash when piped.
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
SKIP_SYM = "[SKIP]"


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


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("OPENALGO_API_KEY", "verify-hc-key")
    env.setdefault("OPENALGO_BASE_URL", "http://127.0.0.1:5000")
    env.setdefault("OPENALGO_MODE", "ANALYZE")
    return env


def run_cmd(cmd: list[str], timeout: int = 300) -> tuple[int, str, str]:
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO_ROOT,
        env=_env(),
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def _print(result: bool, message: str) -> None:
    print(f"{PASS_SYM if result else FAIL_SYM}: {message}")


def check_hc01() -> bool:
    ok = not (REPO_ROOT / "src" / "__init__.py").exists()
    _print(ok, "HC-01 src/__init__.py absent")
    return ok


def check_hc02() -> bool:
    stray = [p for p in REPO_ROOT.glob("src/*.py") if "__pycache__" not in str(p)]
    ok = len(stray) == 0
    _print(ok, f"HC-02 stray src/*.py count={len(stray)} (expect 0)")
    if not ok:
        for p in stray:
            print(f"  stray: {p}")
    return ok


def check_hc03() -> bool:
    empty: list[Path] = []
    loats_dir = REPO_ROOT / "src" / "loats"
    if loats_dir.is_dir():
        for subdir in loats_dir.iterdir():
            if subdir.is_dir() and subdir.name != "__pycache__":
                py_files = list(subdir.rglob("*.py")) + list(subdir.rglob("*.pyi"))
                if not py_files:
                    empty.append(subdir)
    ok = not empty
    _print(ok, f"HC-03 empty package shells count={len(empty)} (expect 0)")
    for p in empty:
        print(f"  empty: {p.relative_to(REPO_ROOT)}")
    return ok


def check_hc04() -> bool:
    ok = (REPO_ROOT / "scripts" / "check_deps_sync.py").exists()
    _print(
        ok, "HC-04 deps-sync script exists" if ok else "HC-04 deps-sync script missing"
    )
    return ok


def check_hc05() -> bool:
    rc, out, err = run_cmd(
        [PY, "-m", "ruff", "check", "src/", "tests/", "--config", "pyproject.toml"],
        timeout=120,
    )
    ok = rc == 0
    _print(ok, "HC-05 ruff check clean" if ok else "HC-05 ruff check failed")
    if not ok:
        print(out)
        print(err)
    return ok


def check_hc06() -> bool:
    rc, out, err = run_cmd(
        [
            PY,
            "-m",
            "ruff",
            "format",
            "--check",
            "src/",
            "tests/",
            "--config",
            "pyproject.toml",
        ],
        timeout=120,
    )
    ok = rc == 0
    _print(ok, "HC-06 ruff format clean" if ok else "HC-06 ruff format failed")
    if not ok:
        print(out)
        print(err)
    return ok


def check_hc07() -> bool:
    rc, out, err = run_cmd(
        [PY, "-m", "isort", "--check-only", "src/", "tests/"], timeout=120
    )
    ok = rc == 0
    _print(ok, "HC-07 isort clean" if ok else "HC-07 isort failed")
    if not ok:
        print(out)
        print(err)
    return ok


def check_hc08() -> bool:
    rc, out, err = run_cmd([PY, "-m", "flake8", "src/", "tests/"], timeout=120)
    ok = rc == 0
    _print(ok, "HC-08 flake8 clean" if ok else "HC-08 flake8 failed")
    if not ok:
        print(out)
        print(err)
    return ok


def check_hc09() -> bool:
    rc, out, err = run_cmd(
        [PY, "-m", "mypy", "src/", "--strict", "--config-file", "pyproject.toml"],
        timeout=300,
    )
    ok = rc == 0
    _print(ok, "HC-09 mypy strict clean" if ok else "HC-09 mypy strict failed")
    if not ok:
        print(out)
        print(err)
    return ok


def check_hc10() -> bool:
    rc, out, err = run_cmd(
        [PY, "-m", "bandit", "-r", "src/", "-c", "pyproject.toml", "-q"],
        timeout=120,
    )
    ok = rc == 0
    _print(ok, "HC-10 bandit clean" if ok else "HC-10 bandit failed")
    if not ok:
        print(out)
        print(err)
    return ok


def check_hc11() -> bool:
    print(f"{SKIP_SYM}: HC-11 pip-audit (requires online connectivity)")
    return True  # not blocking


def check_imports() -> bool:
    code = (
        "import sys; sys.path.insert(0, 'src'); "
        "from loats.strength import StrengthEngine, StrengthSource; "
        "from loats.rules import CMPRulesEngine; "
        "from loats.sizing import SizingEngine; "
        "print('imports ok')"
    )
    result = subprocess.run(
        [PY, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO_ROOT,
        env=_env(),
    )
    ok = "imports ok" in result.stdout
    _print(ok, "post-removal imports ok" if ok else "post-removal imports failed")
    if not ok:
        print(f"  stdout: {result.stdout.strip()}")
        print(f"  stderr: {result.stderr.strip()}")
    return ok


def main() -> int:
    print("=" * 70)
    print("HC-01/02/03 + HC-05/06/07/08/09/10 External Verification")
    print(f"Interpreter: {PY}")
    print("=" * 70)
    results = {
        "HC-01": check_hc01(),
        "HC-02": check_hc02(),
        "HC-03": check_hc03(),
        "HC-04": check_hc04(),
        "HC-05": check_hc05(),
        "HC-06": check_hc06(),
        "HC-07": check_hc07(),
        "HC-08": check_hc08(),
        "HC-09": check_hc09(),
        "HC-10": check_hc10(),
        "HC-11": check_hc11(),
        "IMPORTS": check_imports(),
    }
    print("=" * 70)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"TOTAL: {passed}/{total} passed")
    if passed == total:
        print("ALL CHECKS PASSED")
        return 0
    print("SOME CHECKS FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
