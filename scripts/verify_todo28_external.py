#!/usr/bin/env python3
"""External verification script for TODO-28 (mypy strict clean-up).

This script gives the user an independent, reproducible way to confirm that the
45 mypy strict errors across 8 source files have been resolved and that the
associated runtime behaviour (async DB helpers, trailing-stop orchestration,
audit dual-write, etc.) still works.

Run from the repository root:

    loatsNEW/Scripts/python.exe scripts/verify_todo28_external.py

Exit code 0 means all verification stages passed.
"""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _project_root() -> Path:
    """Resolve project root robustly for direct and health-check invocation."""
    script = Path(__file__).resolve()
    if "scripts" in script.parts:
        idx = script.parts.index("scripts")
        return Path(*script.parts[:idx])
    cwd = Path.cwd()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "src").exists():
            return candidate
    return cwd


ROOT = _project_root()
PY = sys.executable
SRC = ROOT / "src"


def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """Run a command and return (exit_code, stdout, stderr)."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(cwd or ROOT),
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, result.stdout, result.stderr


def _safe_print(msg: str, *, indent: int = 0) -> None:
    """Print verification messages safely on Windows cp1252 pipes."""
    prefix = "  " * indent
    try:
        print(f"{prefix}{msg}")
    except UnicodeEncodeError:
        print(f"{prefix}{msg.encode('ascii', 'replace').decode('ascii')}")


# ---------------------------------------------------------------------------
# Verification stages
# ---------------------------------------------------------------------------


def stage_1_mypy_full_src() -> bool:
    """Verify mypy --strict src/ reports zero errors."""
    _safe_print("[STAGE 1] mypy strict (full src)")
    code, out, err = _run(
        [
            PY,
            "-m",
            "mypy",
            "src/",
            "--strict",
            "--config-file",
            "pyproject.toml",
        ]
    )
    combined = (out + err).strip()
    if code != 0 or (combined and "Success" not in combined):
        _safe_print("FAIL: mypy did not report success", indent=1)
        _safe_print(combined[:800], indent=2)
        return False
    _safe_print(f"PASS: {combined}", indent=1)
    return True


def stage_2_mypy_changed_files() -> bool:
    """Verify mypy --strict on the 8 changed source files is clean."""
    _safe_print("[STAGE 2] mypy strict (changed source files)")
    files = [
        "src/loats/options.py",
        "src/loats/trailing_stop.py",
        "src/loats/sizing.py",
        "src/loats/rules.py",
        "src/loats/performance_analyzer.py",
        "src/loats/database_async_additions.py",
        "src/loats/backtest_sanity.py",
        "src/loats/orchestrator.py",
    ]
    code, out, err = _run(
        [PY, "-m", "mypy", "--strict", "--config-file", "pyproject.toml", *files]
    )
    combined = (out + err).strip()
    if code != 0 or (combined and "Success" not in combined):
        _safe_print("FAIL: mypy reported errors on changed files", indent=1)
        _safe_print(combined[:800], indent=2)
        return False
    _safe_print(f"PASS: {combined}", indent=1)
    return True


def stage_3_ruff_lint_and_format() -> bool:
    """Verify ruff lint and ruff format --check are clean for src/."""
    _safe_print("[STAGE 3] ruff lint + format")
    code, out, err = _run([PY, "-m", "ruff", "check", "src/"])
    if code != 0:
        _safe_print("FAIL: ruff check", indent=1)
        _safe_print((out + err)[:800], indent=2)
        return False
    _safe_print("PASS: ruff check", indent=1)

    code, out, err = _run([PY, "-m", "ruff", "format", "--check", "src/", "tests/"])
    if code != 0:
        _safe_print("FAIL: ruff format --check", indent=1)
        _safe_print((out + err)[:800], indent=2)
        return False
    _safe_print("PASS: ruff format --check", indent=1)
    return True


def stage_4_async_db_helpers() -> bool:
    """Verify Database async helpers are present, typed, and registered."""
    _safe_print("[STAGE 4] async DB helper registration + signatures")
    sys.path.insert(0, str(SRC))
    try:
        from loats.database import Database
        from loats.database_async_additions import extend_database_class
        from loats.models import Position, Trade
    except Exception as exc:  # pragma: no cover - verification only
        _safe_print(f"FAIL: import error {exc}", indent=1)
        return False

    extend_database_class()

    required_public = {
        "async_store_quote",
        "async_store_position",
        "async_get_latest_signals",
        "async_update_trade",
        "async_update_order_status",
        "async_get_trade",
        "async_create_trade_decision",
        "async_log_audit",
        "async_get_historical_data",
    }
    missing = required_public - set(dir(Database))
    if missing:
        _safe_print(f"FAIL: missing public async methods {missing}", indent=1)
        return False
    _safe_print(
        f"PASS: all {len(required_public)} public async methods registered", indent=1
    )

    # Validate signatures for a few critical helpers.
    sig = inspect.signature(Database.async_update_trade)
    params = list(sig.parameters)
    if params != ["self", "trade"]:
        _safe_print(f"FAIL: async_update_trade signature {params}", indent=1)
        return False

    sig = inspect.signature(Database.async_get_latest_signals)
    params = list(sig.parameters)
    if params != ["self", "symbol", "limit", "scan_type"]:
        _safe_print(f"FAIL: async_get_latest_signals signature {params}", indent=1)
        return False

    sig = inspect.signature(Database.async_log_audit)
    params = list(sig.parameters)
    expected = [
        "self",
        "action",
        "entity_type",
        "entity_id",
        "user",
        "metadata",
        "previous_state",
        "new_state",
    ]
    if params != expected:
        _safe_print(f"FAIL: async_log_audit signature {params}", indent=1)
        return False

    # Position has metadata field.
    if "metadata" not in Position.model_fields:
        _safe_print("FAIL: Position missing metadata field", indent=1)
        return False

    # Trade.current_price: options.py uses Trade objects in calculate_portfolio_var
    # and reads current_price from position.metadata (fallback to exit_price/entry_price).
    # Confirm Trade is compatible (metadata field exists, which it does as of the fix).
    if "metadata" not in Trade.model_fields:
        _safe_print("FAIL: Trade missing metadata field", indent=1)
        return False

    _safe_print("PASS: helper signatures and model attributes verified", indent=1)
    return True


def stage_5_audit_dual_write_runtime() -> bool:
    """Run a live dual-write audit test with an injected temp path."""
    _safe_print("[STAGE 5] audit dual-write runtime")
    audit_script = ROOT / "tests" / "test_audit_dual_write.py"
    if not audit_script.exists():
        _safe_print("SKIP: test_audit_dual_write.py not found", indent=1)
        return True
    code, out, err = _run([PY, "-m", "pytest", str(audit_script), "-q", "--tb=short"])
    if code != 0:
        _safe_print("FAIL: audit dual-write tests", indent=1)
        _safe_print((out + err)[:800], indent=2)
        return False
    _safe_print("PASS: audit dual-write tests", indent=1)
    return True


def stage_6_database_async_additions_tests() -> bool:
    """Run the async DB additions test suite."""
    _safe_print("[STAGE 6] database async additions tests")
    test_path = ROOT / "tests" / "test_database_async_additions.py"
    if not test_path.exists():
        _safe_print("SKIP: test_database_async_additions.py not found", indent=1)
        return True
    code, out, err = _run([PY, "-m", "pytest", str(test_path), "-q", "--tb=short"])
    if code != 0:
        _safe_print("FAIL: database async additions tests", indent=1)
        _safe_print((out + err)[:800], indent=2)
        return False
    _safe_print("PASS: database async additions tests", indent=1)
    return True


def stage_7_trailing_stop_and_options_tests() -> bool:
    """Run focused runtime tests for trailing stop and options modules."""
    _safe_print("[STAGE 7] trailing stop + options sanity tests")
    tests = [
        "tests/test_trailing_stop_runtime.py",
        "tests/test_options.py",
    ]
    existing = [str(ROOT / t) for t in tests if (ROOT / t).exists()]
    if not existing:
        _safe_print("SKIP: no trailing stop/options tests found", indent=1)
        return True
    code, out, err = _run([PY, "-m", "pytest", "-q", "--tb=short", *existing])
    if code != 0:
        _safe_print("FAIL: trailing stop / options tests", indent=1)
        _safe_print((out + err)[:800], indent=2)
        return False
    _safe_print("PASS: trailing stop + options tests", indent=1)
    return True


def stage_8_imports_and_bandit() -> bool:
    """Validate imports for changed modules and bandit security scan."""
    _safe_print("[STAGE 8] imports + bandit security")
    modules = [
        "loats.options",
        "loats.trailing_stop",
        "loats.sizing",
        "loats.rules",
        "loats.performance_analyzer",
        "loats.database_async_additions",
        "loats.backtest_sanity",
        "loats.orchestrator",
    ]
    import_cmd = "; ".join(f"import {m}" for m in modules)
    code, out, err = _run([PY, "-c", import_cmd])
    if code != 0:
        _safe_print("FAIL: module imports", indent=1)
        _safe_print((out + err)[:800], indent=2)
        return False
    _safe_print("PASS: changed modules import cleanly", indent=1)

    code, out, err = _run(
        [PY, "-m", "bandit", "-r", "src/", "-c", "pyproject.toml", "-q"]
    )
    if code != 0:
        _safe_print("FAIL: bandit security scan", indent=1)
        _safe_print((out + err)[:800], indent=2)
        return False
    _safe_print("PASS: bandit security scan", indent=1)
    return True


def stage_9_health_check_todo28() -> bool:
    """Confirm FR7 health check T03/T04 pass."""
    _safe_print("[STAGE 9] FR7 health check T03/T04")
    code, out, err = _run([PY, "scripts/fr7_health_check.py", "--only", "T03,T04"])
    if code != 0:
        _safe_print("FAIL: health check T03/T04", indent=1)
        _safe_print((out + err)[:800], indent=2)
        return False
    _safe_print("PASS: health check T03/T04", indent=1)
    return True


def stage_10_no_pytest_bypass() -> bool:
    """Confirm no PYTEST_CURRENT_TEST bypass remains in src/."""
    _safe_print("[STAGE 10] no PYTEST_CURRENT_TEST bypass in src/")
    code, out, _ = _run(["git", "grep", "PYTEST_CURRENT_TEST", "--", "src/"])
    if code == 0 and out.strip():
        _safe_print("FAIL: PYTEST_CURRENT_TEST found in src/", indent=1)
        _safe_print(out[:400], indent=2)
        return False
    _safe_print("PASS: no PYTEST_CURRENT_TEST bypass", indent=1)
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Run all verification stages and report."""
    os.environ.setdefault("PYTHONPATH", str(SRC))

    stages = [
        ("mypy full src", stage_1_mypy_full_src),
        ("mypy changed files", stage_2_mypy_changed_files),
        ("ruff lint + format", stage_3_ruff_lint_and_format),
        ("async DB helper registration", stage_4_async_db_helpers),
        ("audit dual-write runtime", stage_5_audit_dual_write_runtime),
        ("database async additions tests", stage_6_database_async_additions_tests),
        ("trailing stop + options tests", stage_7_trailing_stop_and_options_tests),
        ("imports + bandit", stage_8_imports_and_bandit),
        ("FR7 T03/T04", stage_9_health_check_todo28),
        ("no PYTEST_CURRENT_TEST bypass", stage_10_no_pytest_bypass),
    ]

    _safe_print("=" * 70)
    _safe_print("TODO-28 External Verification (mypy strict clean-up)")
    _safe_print("=" * 70)

    results: list[tuple[str, bool]] = []
    for name, fn in stages:
        ok = fn()
        results.append((name, ok))
        if not ok:
            _safe_print(f"  [FAIL] {name}")
        else:
            _safe_print(f"  [PASS] {name}")

    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    _safe_print("=" * 70)
    _safe_print(f"RESULT: {passed}/{total} stages passed")
    _safe_print("=" * 70)

    if passed == total:
        _safe_print("TODO-28 verification: ALL CLEAR")
        return 0
    _safe_print("TODO-28 verification: FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
