#!/usr/bin/env python3
"""Comprehensive HC registry verification.

Verifies HC-01/02/03 (structural), HC-04 (deps sync), HC-05/06/07/08/09/10
(static-analysis gates), HC-12/13 (coverage), and the new coverage-lift
test suite.

Designed for external confirmation: runs with the project venv, uses no
shell quoting, and prints ASCII-safe PASS/FAIL lines.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Windows UTF-8 stdout/stderr fix (so Unicode symbols do not crash when
# stdout is piped by a health-check wrapper).
# ---------------------------------------------------------------------------
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
INFO_SYM = "[INFO]"


def _resolve_python() -> str:
    """Return the project-venv interpreter when available, else sys.executable."""

    def _has_dev_tools(p: Path) -> bool:
        try:
            return (p.parent.parent / "Lib" / "site-packages" / "ruff").exists() or (
                p.parent.parent / "lib" / "python3.12" / "site-packages" / "ruff"
            ).exists()
        except Exception:
            return False

    candidates = [
        REPO_ROOT / "loatsNEW" / "Scripts" / "python.exe",
        REPO_ROOT / "loatsNEW" / "bin" / "python",
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "bin" / "python",
    ]
    for cand in candidates:
        if cand.exists() and _has_dev_tools(cand):
            return str(cand)
    for cand in candidates:
        if cand.exists():
            return str(cand)
    return sys.executable


PY = _resolve_python()


def _child_env() -> dict[str, str]:
    """Environment handed to every subprocess probe."""
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    # Settings may validate these on import; harmless defaults.
    env.setdefault("OPENALGO_API_KEY", "verify-hc-key")
    env.setdefault("OPENALGO_BASE_URL", "http://127.0.0.1:5000")
    env.setdefault("OPENALGO_MODE", "ANALYZE")
    return env


def run_cmd(
    cmd: list[str],
    cwd: Path = REPO_ROOT,
    timeout: int = 300,
) -> tuple[int, str, str]:
    """Run a command without shell interpolation and return (rc, stdout, stderr)."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        env=_child_env(),
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def _print(result: bool, message: str) -> None:
    print(f"{PASS_SYM if result else FAIL_SYM}: {message}")


def check_hc01() -> bool:
    """HC-01: src/__init__.py must be absent."""
    ok = not (REPO_ROOT / "src" / "__init__.py").exists()
    _print(ok, "HC-01 src/__init__.py absent")
    return ok


def check_hc02() -> bool:
    """HC-02: no stray .py files directly under src/."""
    stray = [p for p in REPO_ROOT.glob("src/*.py") if "__pycache__" not in str(p)]
    ok = len(stray) == 0
    _print(ok, f"HC-02 stray src/*.py count={len(stray)} (expect 0)")
    if not ok:
        for p in stray:
            print(f"  stray: {p}")
    return ok


def check_hc03() -> bool:
    """HC-03: no empty Python package shells under src/loats/."""
    empty_shells: list[Path] = []
    loats_dir = REPO_ROOT / "src" / "loats"
    if loats_dir.is_dir():
        # Tooling exhaust (mypy/pylint caches) is not package structure; skip
        # any directory git already ignores (dot-prefixed caches at minimum).
        skip_names = {"__pycache__"}
        for subdir in loats_dir.iterdir():
            if subdir.is_dir() and subdir.name not in skip_names:
                if subdir.name.startswith("."):
                    continue  # dot-prefixed tool caches (.mypy_cache, .ruff_cache)
                py_files = list(subdir.rglob("*.py")) + list(subdir.rglob("*.pyi"))
                if not py_files:
                    empty_shells.append(subdir)
    ok = not empty_shells
    _print(ok, f"HC-03 empty package shells count={len(empty_shells)} (expect 0)")
    for s in empty_shells:
        print(f"  empty: {s.relative_to(REPO_ROOT)}")
    return ok


def check_hc04() -> bool:
    """HC-04: dependency sync script exists."""
    ok = (REPO_ROOT / "scripts" / "check_deps_sync.py").exists()
    _print(
        ok, "HC-04 deps-sync script exists" if ok else "HC-04 deps-sync script missing"
    )
    return ok


def check_hc05_ruff_check() -> bool:
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


def check_hc06_ruff_format() -> bool:
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


def check_hc07_isort() -> bool:
    rc, out, err = run_cmd(
        [PY, "-m", "isort", "--check-only", "src/", "tests/"], timeout=120
    )
    ok = rc == 0
    _print(ok, "HC-07 isort clean" if ok else "HC-07 isort failed")
    if not ok:
        print(out)
        print(err)
    return ok


def check_hc08_flake8() -> bool:
    rc, out, err = run_cmd([PY, "-m", "flake8", "src/", "tests/"], timeout=120)
    ok = rc == 0
    _print(ok, "HC-08 flake8 clean" if ok else "HC-08 flake8 failed")
    if not ok:
        print(out)
        print(err)
    return ok


def check_hc09_mypy() -> bool:
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


def check_hc10_bandit() -> bool:
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


def check_gates() -> bool:
    """HC-05 through HC-10."""
    return all(
        [
            check_hc05_ruff_check(),
            check_hc06_ruff_format(),
            check_hc07_isort(),
            check_hc08_flake8(),
            check_hc09_mypy(),
            check_hc10_bandit(),
        ]
    )


def check_coverage() -> bool:
    """HC-12 aggregate >=80% and HC-13 per-module floors.

    coverage.json is a gitignored run artifact (F8-M-05 class): it is
    produced by the CI pytest-coverage step and is absent on a fresh
    clone. Rather than failing on the missing file, self-measure by
    running the same pytest --cov command CI uses and KEEP the artifact
    (gitignored, regenerated by every coverage run): the HC registry
    delegates to this script once per HC-01..HC-13 row, so cleaning up
    here would force 13 full-suite re-measurements per registry pass.
    """
    cov_file = REPO_ROOT / "coverage.json"
    if not cov_file.exists():
        print(
            f"{INFO_SYM}: HC-12 coverage.json not found; self-measuring "
            "(pytest --cov, may take a few minutes)"
        )
        rc, out, err = run_cmd(
            [
                PY,
                "-m",
                "pytest",
                "tests/",
                "-q",
                "-p",
                "no:cacheprovider",
                "--cov=src",
                "--cov-branch",
                "--cov-fail-under=80",
                "--cov-report=json:coverage.json",
            ],
            timeout=1200,
        )
        if not cov_file.exists():
            print(
                f"{FAIL_SYM}: HC-12 self-measure failed to produce "
                f"coverage.json (pytest rc={rc})"
            )
            if out.strip():
                print(out.strip().splitlines()[-1])
            return False

    try:
        with open(cov_file, encoding="utf-8") as f:
            data = json.load(f)
        agg_pct = data["totals"]["percent_covered"]
    except Exception as exc:
        print(f"{FAIL_SYM}: HC-12 unable to read coverage.json: {exc}")
        return False

    agg_ok = agg_pct >= 80.0
    _print(agg_ok, f"HC-12 aggregate coverage {agg_pct:.1f}% (>=80%)")

    rc, out, err = run_cmd([PY, "scripts/check_per_module_coverage.py"], timeout=60)
    floors_ok = rc == 0
    _print(
        floors_ok,
        "HC-13 per-module coverage floors ALL MET"
        if floors_ok
        else "HC-13 per-module coverage floors FAILED",
    )
    if out.strip():
        for line in out.strip().splitlines():
            print(f"  {line}")
    if err.strip():
        for line in err.strip().splitlines():
            print(f"  {line}")
    return agg_ok and floors_ok


def check_new_tests() -> bool:
    """New coverage lift tests for performance_analyzer, rules, sizing."""
    rc, out, err = run_cmd(
        [
            PY,
            "-m",
            "pytest",
            "tests/test_performance_analyzer.py",
            "tests/test_rules_engine.py",
            "tests/test_sizing_engine.py",
            "-q",
            "--tb=short",
        ],
        timeout=120,
    )
    ok = rc == 0
    _print(
        ok, "New coverage lift tests passed" if ok else "New coverage lift tests failed"
    )
    summary = ""
    for line in reversed(out.splitlines()):
        if "passed" in line or "failed" in line or "error" in line.lower():
            summary = line.strip()
            break
    if summary:
        print(f"  {summary}")
    if not ok and err.strip():
        for line in err.strip().splitlines()[:20]:
            print(f"  {line}")
    return ok


def main() -> int:
    print("=" * 70)
    print("COMPREHENSIVE HC REGISTRY VERIFICATION")
    print(f"Interpreter: {PY}")
    print("=" * 70)

    results = [
        ("HC-01", check_hc01()),
        ("HC-02", check_hc02()),
        ("HC-03", check_hc03()),
        ("HC-04", check_hc04()),
        ("GATES", check_gates()),
        ("HC-12/13", check_coverage()),
        ("NEW_TESTS", check_new_tests()),
    ]

    print("=" * 70)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"TOTAL: {passed}/{total} categories passed")
    if passed == total:
        print("ALL CHECKS PASSED - BUILD IMPLEMENTATION SUCCESSFUL")
        return 0
    print("SOME CHECKS FAILED - REVIEW DETAILS ABOVE")
    return 1


if __name__ == "__main__":
    sys.exit(main())
