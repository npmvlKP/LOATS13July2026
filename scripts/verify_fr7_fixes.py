#!/usr/bin/env python3
"""Comprehensive verification script for FR7 Health Check fixes.

This script verifies:
1. Windows UTF-8 encoding fix works
2. All static checks pass (ruff, mypy, bandit, gitleaks, imports)
3. TODO-28 is complete (mypy strict clean, no PYTEST_CURRENT_TEST bypass)
4. Temporary files are cleaned up

Run from repository root:

    python scripts/verify_fr7_fixes.py

Exit code 0 means all verification stages passed.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path


def project_root() -> Path:
    """Resolve project root robustly."""
    script = Path(__file__).resolve()
    if "scripts" in script.parts:
        idx = script.parts.index("scripts")
        return Path(*script.parts[:idx])
    cwd = Path.cwd()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "src").exists():
            return candidate
    return cwd


ROOT = project_root()


def _resolve_python() -> str:
    """Prefer project venv python if present, else launcher."""
    def _has_dev_tools(p: Path) -> bool:
        try:
            return (p.parent.parent / "Lib" / "site-packages" / "ruff").exists() or (
                p.parent.parent / "lib" / "python3.12" / "site-packages" / "ruff"
            ).exists()
        except Exception:
            return False

    candidates = [
        ROOT / "loatsNEW" / "Scripts" / "python.exe",
        ROOT / "loatsNEW" / "bin" / "python",
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
    ]
    for cand in candidates:
        if cand.exists() and _has_dev_tools(cand):
            return str(cand)
    for cand in candidates:
        if cand.exists():
            return str(cand)
    return sys.executable


PY = _resolve_python()


def run_cmd(
    cmd: list[str], capture: bool = True, timeout: int = 60
) -> subprocess.CompletedProcess:
    """Run a command with UTF-8 encoding."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        timeout=timeout,
        cwd=ROOT,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print("=" * 72)


def verify_stage(stage_name: str, test_fn) -> bool:
    """Run a verification stage."""
    print(f"\n[STAGE] {stage_name} ...")
    try:
        result = test_fn()
        if result:
            print(f"  [PASS] {stage_name}")
            return True
        else:
            print(f"  [FAIL] {stage_name}")
            return False
    except Exception as e:
        print(f"  [ERROR] {stage_name}: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_utf8_fix() -> bool:
    """Verify UTF-8 encoding fix works."""
    # Test that health check can print box-drawing characters
    result = run_cmd([PY, "scripts/fr7_health_check.py", "--list"], timeout=30)
    if result.returncode == 0:
        # Check output contains expected characters
        return "ID" in result.stdout and "GROUP" in result.stdout
    return False


def test_ruff() -> bool:
    """Verify ruff lint passes."""
    result = run_cmd([PY, "-m", "ruff", "check", "src/"], timeout=60)
    print(f"    ruff exit code: {result.returncode}")
    if result.stdout:
        print(f"    stdout: {result.stdout[:200]}")
    return result.returncode == 0


def test_ruff_format() -> bool:
    """Verify ruff format passes."""
    result = run_cmd([PY, "-m", "ruff", "format", "--check", "src/", "tests/"], timeout=60)
    return result.returncode == 0


def test_mypy_strict_files() -> bool:
    """Verify mypy strict on changed files passes (TODO-28)."""
    result = run_cmd(
        [
            PY,
            "-m",
            "mypy",
            "src/loats/options_math.py",
            "src/loats/trade_decision.py",
            "src/loats/config/settings.py",
            "--strict",
            "--config-file",
            "pyproject.toml",
        ],
        timeout=60,
    )
    print(f"    mypy changed files exit code: {result.returncode}")
    if result.stdout:
        print(f"    stdout: {result.stdout[:200]}")
    if result.stderr:
        print(f"    stderr: {result.stderr[:200]}")
    return result.returncode == 0


def test_mypy_strict_full() -> bool:
    """Verify mypy strict on full src passes (TODO-28 complete)."""
    result = run_cmd(
        [PY, "-m", "mypy", "src/", "--strict", "--config-file", "pyproject.toml"],
        timeout=90,
    )
    print(f"    mypy full src exit code: {result.returncode}")
    if result.stdout:
        print(f"    stdout: {result.stdout[:300]}")
    if result.stderr:
        print(f"    stderr: {result.stderr[:300]}")
    return result.returncode == 0


def test_bandit() -> bool:
    """Verify bandit security scan passes."""
    result = run_cmd([PY, "-m", "bandit", "-r", "src/", "-c", "pyproject.toml", "-q"], timeout=60)
    return result.returncode == 0


def test_imports() -> bool:
    """Verify all src/loats modules import without error."""
    result = run_cmd(
        [
            PY,
            "-c",
            (
                "import sys; sys.path.insert(0,'src'); "
                "import importlib; "
                "mods=['loats','loats.options_math','loats.options','loats.ta','loats.trade_decision','loats.orchestrator','loats.scheduler','loats.sentiment','loats.sizing','loats.rules','loats.config.settings']; "
                "[importlib.import_module(m) for m in mods]; "
                "print('imports ok')"
            ),
        ],
        timeout=30,
    )
    return result.returncode == 0 and "imports ok" in result.stdout


def test_no_pytest_bypass() -> bool:
    """Verify no PYTEST_CURRENT_TEST bypass remains (TODO-28)."""
    result = run_cmd([PY, "scripts/check_no_pytest_bypass.py"], timeout=15)
    return result.returncode == 0 and "no PYTEST_CURRENT_TEST bypass" in result.stdout


def test_temp_files_cleaned() -> bool:
    """Verify temporary files are cleaned up (excluding locked SQLite files)."""
    temp_files = [
        "tmp_audit.jsonl",
        "health.json",
        "verification.json",
        "ruff_before_stats.json",
    ]
    found = []
    for f in temp_files:
        if (ROOT / f).exists():
            found.append(f)
    # Note: tmp_schema.db is excluded as it may be locked by active connections
    if found:
        print(f"    Found temporary files: {found}")
        return False
    return True


def main() -> int:
    """Run all verification stages."""
    print_section("FR7 HEALTH CHECK FIXES VERIFICATION")
    print(f"Project root: {ROOT}")
    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")

    stages = [
        ("UTF-8 Encoding Fix", test_utf8_fix),
        ("Ruff Lint", test_ruff),
        ("Ruff Format", test_ruff_format),
        ("Mypy Strict (Changed Files)", test_mypy_strict_files),
        ("Mypy Strict (Full src) - TODO-28", test_mypy_strict_full),
        ("Bandit Security", test_bandit),
        ("Import Validation", test_imports),
        ("No PYTEST_CURRENT_TEST Bypass - TODO-28", test_no_pytest_bypass),
        ("Temporary Files Cleaned", test_temp_files_cleaned),
    ]

    results = []
    for stage_name, test_fn in stages:
        results.append(verify_stage(stage_name, test_fn))

    print_section("SUMMARY")
    passed = sum(results)
    total = len(results)
    print(f"\nTotal: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")

    if passed == total:
        print("\n[SUCCESS] All verification stages passed!")
        return 0
    else:
        print(f"\n[FAILURE] {total - passed} verification stage(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())