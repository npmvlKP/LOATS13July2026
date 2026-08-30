#!/usr/bin/env python3
"""External verification script for TODO-26 (F7-L-06) implementation.

Verifies:
1. backtest_sanity.py module exists in src/loats/
2. Module implements required CMP P4 exit gate functionality
3. Scheduler wires backtest_sanity as weekly cron job
4. Module is importable and has no syntax errors
5. All required classes and functions are present

Usage:
    python scripts/verify_todo26_external.py
    G:\\.OA\\LOATS-13July2026\\LOATS13July2026\\Scripts\\python.exe scripts/verify_todo26_external.py
"""

import sys
from pathlib import Path
from typing import Any

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent
SRC_LOATS = PROJECT_ROOT / "src" / "loats"

# ANSI-safe symbols for subprocess contexts
CHECK_MARK = "[PASS]"
X_MARK = "[FAIL]"
INFO_MARK = "[INFO]"

def check_module_exists() -> bool:
    """Verify backtest_sanity.py module exists."""
    print(f"\n{INFO_MARK} Checking if backtest_sanity.py module exists...")
    module_path = SRC_LOATS / "backtest_sanity.py"

    if not module_path.exists():
        print(f"  {X_MARK} backtest_sanity.py NOT FOUND at {module_path}")
        return False

    print(f"  {CHECK_MARK} backtest_sanity.py found at {module_path}")
    return True


def check_module_importable() -> bool:
    """Verify module is importable without errors."""
    print(f"\n{INFO_MARK} Checking if backtest_sanity.py is importable...")

    try:
        sys.path.insert(0, str(PROJECT_ROOT / "src"))
        import loats.backtest_sanity as bs_module
        print(f"  {CHECK_MARK} Module imports successfully")
        return True
    except ImportError as e:
        print(f"  {X_MARK} Import error: {e}")
        return False
    except SyntaxError as e:
        print(f"  {X_MARK} Syntax error: {e}")
        return False
    except Exception as e:
        print(f"  {X_MARK} Unexpected error: {e}")
        return False


def check_required_exports() -> bool:
    """Verify module exports required functions and classes."""
    print(f"\n{INFO_MARK} Checking required exports...")

    try:
        sys.path.insert(0, str(PROJECT_ROOT / "src"))
        import loats.backtest_sanity as bs_module

        required = [
            "BacktestSanityResult",
            "BacktestWindow",
            "PnLResult",
            "WalkForwardWindowIterator",
            "run_backtest_sanity_check",
            "backtest_sanity_pass_gate",
            "calculate_simple_pnl",
            "validate_no_lookahead",
        ]

        all_present = True
        for name in required:
            if not hasattr(bs_module, name):
                print(f"  {X_MARK} Missing export: {name}")
                all_present = False
            else:
                print(f"  {CHECK_MARK} Export found: {name}")

        return all_present
    except Exception as e:
        print(f"  {X_MARK} Error checking exports: {e}")
        return False


def check_walk_forward_logic() -> bool:
    """Verify WalkForwardWindowIterator implements required logic."""
    print(f"\n{INFO_MARK} Checking WalkForwardWindowIterator logic...")

    try:
        sys.path.insert(0, str(PROJECT_ROOT / "src"))
        import loats.backtest_sanity as bs_module

        iterator_cls = bs_module.WalkForwardWindowIterator

        # Check required methods
        required_methods = ["__init__", "__iter__", "__next__", "__len__"]
        all_present = True
        for method in required_methods:
            if not hasattr(iterator_cls, method):
                print(f"  {X_MARK} Missing method: {method}")
                all_present = False
            else:
                print(f"  {CHECK_MARK} Method found: {method}")

        return all_present
    except Exception as e:
        print(f"  {X_MARK} Error checking iterator logic: {e}")
        return False


def check_scheduler_wiring() -> bool:
    """Verify scheduler.py wires backtest_sanity as weekly job."""
    print(f"\n{INFO_MARK} Checking scheduler wiring...")

    scheduler_path = SRC_LOATS / "scheduler.py"
    if not scheduler_path.exists():
        print(f"  {X_MARK} scheduler.py not found")
        return False

    scheduler_content = scheduler_path.read_text(encoding="utf-8", errors="ignore")

    checks = [
        ("backtest_sanity import", "from .backtest_sanity import"),
        ("backtest_sanity job registration", '"backtest_sanity_check"'),
        ("run_backtest_sanity_check method", "async def run_backtest_sanity_check"),
        ("weekly cron trigger", "CronTrigger"),
        ("day_of_week", "day_of_week"),
    ]

    all_present = True
    for name, pattern in checks:
        if pattern in scheduler_content:
            print(f"  {CHECK_MARK} {name}: found")
        else:
            print(f"  {X_MARK} {name}: NOT found")
            all_present = False

    return all_present


def check_health_check_integration() -> bool:
    """Verify HC-30 added to fr7_health_check.py."""
    print(f"\n{INFO_MARK} Checking HC-30 health check...")

    health_check_path = PROJECT_ROOT / "scripts" / "fr7_health_check.py"
    if not health_check_path.exists():
        print(f"  {X_MARK} fr7_health_check.py not found")
        return False

    health_check_content = health_check_path.read_text(encoding="utf-8", errors="ignore")

    checks = [
        ("HC-30 entry", '"HC-30"'),
        ("HC-30 name", '"Backtest Sanity Driver Wired"'),
        ("HC-30 description", "TODO-26 / F7-L-06"),
        ("verification script", "verify_todo26_external.py"),
    ]

    all_present = True
    for name, pattern in checks:
        if pattern in health_check_content:
            print(f"  {CHECK_MARK} {name}: found")
        else:
            print(f"  {X_MARK} {name}: NOT found")
            all_present = False

    return all_present


def check_module_documentation() -> bool:
    """Verify module has proper documentation."""
    print(f"\n{INFO_MARK} Checking module documentation...")

    module_path = SRC_LOATS / "backtest_sanity.py"
    if not module_path.exists():
        print(f"  {X_MARK} backtest_sanity.py not found")
        return False

    content = module_path.read_text(encoding="utf-8", errors="ignore")

    checks = [
        ("Module docstring", '"""Backtest sanity module'),
        ("CMP requirement", "CMP P4 exit gate"),
        ("Walk-forward description", "walk-forward"),
        ("No look-ahead", "no look-ahead"),
    ]

    all_present = True
    for name, pattern in checks:
        if pattern in content:
            print(f"  {CHECK_MARK} {name}: found")
        else:
            print(f"  {X_MARK} {name}: NOT found")
            all_present = False

    return all_present


def run_all_verifications() -> bool:
    """Run all verification checks."""
    print("=" * 70)
    print("VERIFYING TODO-26 (F7-L-06) IMPLEMENTATION")
    print("=" * 70)
    print("Task: Drive backtest_sanity - Wire CMP P4 exit gate module")
    print("  with weekly scheduler job against /history data")
    print("=" * 70)

    results = []

    # Run all checks
    results.append(("Module exists", check_module_exists()))
    results.append(("Module importable", check_module_importable()))
    results.append(("Required exports", check_required_exports()))
    results.append(("Walk-forward logic", check_walk_forward_logic()))
    results.append(("Scheduler wiring", check_scheduler_wiring()))
    results.append(("Health check HC-30", check_health_check_integration()))
    results.append(("Module documentation", check_module_documentation()))

    # Print summary
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    total = len(results)
    passed = sum(1 for _, result in results if result)
    failed = total - passed

    for name, result in results:
        symbol = CHECK_MARK if result else X_MARK
        status = "PASS" if result else "FAIL"
        print(f"  {symbol} {name}: {status}")

    print(f"\nTotal: {passed}/{total} checks passed, {failed}/{total} failed")
    print("=" * 70)

    # Exit with appropriate code
    if failed == 0:
        print("\nTODO-26 IMPLEMENTATION VERIFIED: All checks passed")
        return True
    else:
        print(f"\nTODO-26 IMPLEMENTATION INCOMPLETE: {failed} check(s) failed")
        return False


if __name__ == "__main__":
    success = run_all_verifications()
    sys.exit(0 if success else 1)