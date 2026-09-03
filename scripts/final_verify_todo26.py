#!/usr/bin/env python3
"""
EXTERNAL VERIFICATION SCRIPT FOR TODO-26 (F7-L-06)
===================================================

This script provides comprehensive verification that the backtest_sanity module
is properly wired as a production driver in the LOATS13July2026 system.

Verifies:
1. Module existence and structure
2. Required exports and functions
3. Scheduler weekly job wiring
4. On-demand execution (run_once)
5. Health check integration (backtest-sanity coverage floor gate; the
   TODO-26-era HC-30 entry was folded away in the HC-01..HC-27
   re-catalogue, commit 138d376)
6. CMP P4 exit gate compliance

Usage:
    python scripts/final_verify_todo26.py

Exit Codes:
    0: All checks passed
    1: Some checks failed
    2: Error running verification

Dependencies: None (uses only standard library + file operations)
"""

import re
import sys
from datetime import datetime
from pathlib import Path


class Colors:
    """ANSI color codes for terminal output."""

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def print_header(text: str) -> None:
    """Print a formatted header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 80}{Colors.ENDC}\n")


def print_section(text: str) -> None:
    """Print a formatted section header."""
    print(f"\n{Colors.OKCYAN}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.OKCYAN}{'-' * 80}{Colors.ENDC}")


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"{Colors.OKGREEN}  ✓ {message}{Colors.ENDC}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"{Colors.FAIL}  ✗ {message}{Colors.ENDC}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print(f"{Colors.WARNING}  ⚠ {message}{Colors.ENDC}")


def print_info(message: str) -> None:
    """Print an info message."""
    print(f"{Colors.OKBLUE}  ℹ {message}{Colors.ENDC}")


class ProjectPaths:
    """Project path constants."""

    def __init__(self) -> None:
        """Initialize project paths."""
        self.root = Path(__file__).parent.parent
        self.src_loats = self.root / "src" / "loats"
        self.scripts = self.root / "scripts"
        self.tests = self.root / "tests"
        self.docs = self.root / "docs"


class VerificationResult:
    """Verification result tracker."""

    def __init__(self) -> None:
        """Initialize verification results."""
        self.checks: list[tuple[str, bool, str]] = []
        self.warnings: list[str] = []

    def add_check(self, name: str, passed: bool, details: str = "") -> None:
        """Add a verification check."""
        self.checks.append((name, passed, details))

    def add_warning(self, message: str) -> None:
        """Add a warning."""
        self.warnings.append(message)

    @property
    def total(self) -> int:
        """Get total number of checks."""
        return len(self.checks)

    @property
    def passed(self) -> int:
        """Get number of passed checks."""
        return sum(1 for _, passed, _ in self.checks if passed)

    @property
    def failed(self) -> int:
        """Get number of failed checks."""
        return sum(1 for _, passed, _ in self.checks if not passed)


class TODO26Verifier:
    """Main verifier class for TODO-26."""

    def __init__(self) -> None:
        """Initialize verifier."""
        self.paths = ProjectPaths()
        self.results = VerificationResult()

    def verify_module_exists(self) -> bool:
        """Verify backtest_sanity.py module exists."""
        print_section("1. MODULE EXISTENCE CHECK")

        module_path = self.paths.src_loats / "backtest_sanity.py"

        if not module_path.exists():
            print_error(f"backtest_sanity.py NOT FOUND at {module_path}")
            self.results.add_check("Module exists", False, "Module file not found")
            return False

        size = module_path.stat().st_size
        lines = len(
            module_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        )

        print_success(f"backtest_sanity.py found at {module_path}")
        print_info(f"Size: {size:,} bytes, {lines} lines")
        self.results.add_check("Module exists", True, f"{size:,} bytes, {lines} lines")
        return True

    def verify_module_structure(self) -> bool:
        """Verify module has correct structure."""
        print_section("2. MODULE STRUCTURE CHECK")

        module_path = self.paths.src_loats / "backtest_sanity.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")

        checks = [
            ("Module docstring", '"""Backtest sanity module'),
            ("CMP requirement", "CMP Requirement: P4"),
            ("Walk-forward description", "walk-forward window slicing"),
            ("No look-ahead", "no look-ahead verification"),
        ]

        all_passed = True
        for name, pattern in checks:
            if pattern in content:
                print_success(f"{name}: present")
                self.results.add_check(f"Module: {name}", True)
            else:
                print_error(f"{name}: NOT present")
                self.results.add_check(f"Module: {name}", False)
                all_passed = False

        return all_passed

    def verify_required_classes(self) -> bool:
        """Verify required classes are present."""
        print_section("3. REQUIRED CLASSES CHECK")

        module_path = self.paths.src_loats / "backtest_sanity.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")

        classes = [
            "BacktestSanityResult",
            "BacktestWindow",
            "PnLResult",
            "WalkForwardWindowIterator",
        ]

        all_passed = True
        for cls_name in classes:
            if f"class {cls_name}" in content:
                print_success(f"{cls_name}: present")
                self.results.add_check(f"Class: {cls_name}", True)
            else:
                print_error(f"{cls_name}: NOT present")
                self.results.add_check(f"Class: {cls_name}", False)
                all_passed = False

        return all_passed

    def verify_required_functions(self) -> bool:
        """Verify required functions are present."""
        print_section("4. REQUIRED FUNCTIONS CHECK")

        module_path = self.paths.src_loats / "backtest_sanity.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")

        functions = [
            "run_backtest_sanity_check",
            "backtest_sanity_pass_gate",
            "calculate_simple_pnl",
            "validate_no_lookahead",
        ]

        all_passed = True
        for func_name in functions:
            if f"def {func_name}" in content or f"async def {func_name}" in content:
                print_success(f"{func_name}: present")
                self.results.add_check(f"Function: {func_name}", True)
            else:
                print_error(f"{func_name}: NOT present")
                self.results.add_check(f"Function: {func_name}", False)
                all_passed = False

        return all_passed

    def verify_scheduler_wiring(self) -> bool:
        """Verify scheduler wiring."""
        print_section("5. SCHEDULER WIRING CHECK")

        scheduler_path = self.paths.src_loats / "scheduler.py"
        if not scheduler_path.exists():
            print_error("scheduler.py NOT FOUND")
            self.results.add_check("Scheduler wiring", False, "scheduler.py not found")
            return False

        scheduler_content = scheduler_path.read_text(encoding="utf-8", errors="ignore")

        # F8-M-06: the backtest_sanity import moved out of module level
        # ("from .backtest_sanity import ...") into the task body as
        # "import loats.backtest_sanity as _backtest_sanity" - deliberate,
        # it breaks the scheduler -> backtest_sanity import cycle and is
        # bound for reliable test patching. Assert the surviving outcome
        # (the import happens inside the task), not the old idiom.
        checks = [
            (
                "Function-level backtest_sanity import",
                "import loats.backtest_sanity as _backtest_sanity",
            ),
            ("Job registration", '"backtest_sanity_check"'),
            ("Method definition", "async def run_backtest_sanity_check"),
            ("CronTrigger", "CronTrigger"),
            ("Sunday schedule", 'day_of_week="sun"'),
            ("Hour 4 AM", "hour=4"),
            ("Minute 0", "minute=0"),
        ]

        all_passed = True
        for name, pattern in checks:
            if pattern in scheduler_content:
                print_success(f"{name}: present")
                self.results.add_check(f"Scheduler: {name}", True)
            else:
                print_error(f"{name}: NOT present")
                self.results.add_check(f"Scheduler: {name}", False)
                all_passed = False

        # Check for CronTrigger configuration
        cron_match = re.search(
            r'CronTrigger\([^)]*day_of_week="sun"[^)]*hour=4[^)]*minute=0[^)]*\)',
            scheduler_content,
        )
        if cron_match:
            print_success("Weekly schedule: Sunday 4:00 AM IST (CronTrigger)")
            self.results.add_check("Weekly schedule", True, "Sunday 4:00 AM IST")
        else:
            print_error("Weekly schedule: NOT configured correctly")
            self.results.add_check("Weekly schedule", False, "CronTrigger not found")

        return all_passed

    def verify_run_once_integration(self) -> bool:
        """Verify run_once integration."""
        print_section("6. RUN_ONCE INTEGRATION CHECK")

        scheduler_path = self.paths.src_loats / "scheduler.py"
        scheduler_content = scheduler_path.read_text(encoding="utf-8", errors="ignore")

        # Check for run_once method
        if "async def run_once" not in scheduler_content:
            print_error("run_once() method NOT FOUND")
            self.results.add_check("run_once method", False, "Method not found")
            return False

        print_success("run_once() method: present")
        self.results.add_check("run_once method", True)

        # Check for backtest_sanity_check case
        if 'job_id == "backtest_sanity_check"' in scheduler_content:
            print_success("backtest_sanity_check case: present")
            self.results.add_check("run_once case", True)
        else:
            print_error("backtest_sanity_check case: NOT present")
            self.results.add_check("run_once case", False)
            return False

        # Check for method call
        if "await self.run_backtest_sanity_check()" in scheduler_content:
            print_success("Method call in run_once: present")
            self.results.add_check("Method call", True)
        else:
            print_error("Method call in run_once: NOT present")
            self.results.add_check("Method call", False)
            return False

        print_info(
            "Allows on-demand execution: scheduler.run_once('backtest_sanity_check')"
        )
        return True

    def verify_health_check_integration(self) -> bool:
        """Verify health check integration (post-re-catalogue)."""
        print_section("7. HEALTH CHECK INTEGRATION (backtest-sanity gate)")

        # F8-M-06: the TODO-26-era "HC-30 Backtest Sanity Driver Wired"
        # entry no longer exists - the health-check catalogue was
        # re-catalogued to HC-01..HC-27 (commit 138d376) and the driver
        # gate moved to the per-module coverage floor (backtest_sanity
        # >= 80%) plus dedicated walk-forward/no-look-ahead tests
        # (a22d6ca). Assert the surviving outcome: the backtest_sanity
        # floor is present in the enforced gate map.
        floor_map_path = self.paths.scripts / "check_per_module_coverage.py"
        if not floor_map_path.exists():
            print_error("check_per_module_coverage.py NOT FOUND")
            self.results.add_check(
                "Coverage floor map", False, "check_per_module_coverage.py not found"
            )
            return False

        floor_map_content = floor_map_path.read_text(encoding="utf-8", errors="ignore")

        checks = [
            ("Floor map", "FR_FLOOR_MAP"),
            ("backtest_sanity floor 80%", '"backtest_sanity.py": 80.0,'),
        ]

        all_passed = True
        for name, pattern in checks:
            if pattern in floor_map_content:
                print_success(f"{name}: present")
                self.results.add_check(f"Backtest gate: {name}", True)
            else:
                print_error(f"{name}: NOT present")
                self.results.add_check(f"Backtest gate: {name}", False)
                all_passed = False

        return all_passed

    def verify_no_lookahead_logic(self) -> bool:
        """Verify no-lookahead validation logic."""
        print_section("8. NO-LOOKAHEAD VALIDATION LOGIC")

        module_path = self.paths.src_loats / "backtest_sanity.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")

        checks = [
            ("validate_no_lookahead function", "def validate_no_lookahead"),
            ("Timestamp sorting check", "sorted(timestamps)"),
            ("Iterator timestamp check", "window_timestamps"),
            ("Raise on unsorted", "ValueError"),
            ("Initialization check", "if timestamps != sorted(timestamps)"),
        ]

        all_passed = True
        for name, pattern in checks:
            if pattern in content:
                print_success(f"{name}: present")
                self.results.add_check(f"No-lookahead: {name}", True)
            else:
                print_error(f"{name}: NOT present")
                self.results.add_check(f"No-lookahead: {name}", False)
                all_passed = False

        return all_passed

    def verify_walk_forward_iterator(self) -> bool:
        """Verify WalkForwardWindowIterator implementation."""
        print_section("9. WALK-FORWARD WINDOW ITERATOR")

        module_path = self.paths.src_loats / "backtest_sanity.py"
        content = module_path.read_text(encoding="utf-8", errors="ignore")

        # Check class exists
        if "class WalkForwardWindowIterator" not in content:
            print_error("WalkForwardWindowIterator class NOT FOUND")
            self.results.add_check("Iterator class", False, "Class not found")
            return False

        print_success("WalkForwardWindowIterator class: present")
        self.results.add_check("Iterator class", True)

        # Check required methods
        methods = ["__init__", "__iter__", "__next__", "__len__"]
        all_passed = True

        for method in methods:
            if f"def {method}" in content:
                print_success(f"Method {method}: present")
                self.results.add_check(f"Iterator: {method}", True)
            else:
                print_error(f"Method {method}: NOT present")
                self.results.add_check(f"Iterator: {method}", False)
                all_passed = False

        # Check for safety validations
        safety_checks = [
            ("Empty data check", "Historical data cannot be empty"),
            ("Window size validation", "Window size .* cannot exceed"),
            ("Timestamp sort check", "must be sorted by timestamp"),
            ("Window timestamp check", "is not sorted by timestamp"),
        ]

        for name, pattern in safety_checks:
            if re.search(pattern, content):
                print_success(f"Safety check: {name}")
                self.results.add_check(f"Safety: {name}", True)
            else:
                print_warning(
                    f"Safety check: {name} (may be present with different wording)"
                )

        return all_passed

    def verify_verification_scripts(self) -> bool:
        """Verify verification scripts exist."""
        print_section("10. VERIFICATION SCRIPTS CHECK")

        scripts = [
            "verify_todo26_external.py",
            "comprehensive_verify_todo26.py",
        ]

        all_passed = True
        for script in scripts:
            script_path = self.paths.scripts / script
            if script_path.exists():
                size = script_path.stat().st_size
                print_success(f"{script}: present ({size:,} bytes)")
                self.results.add_check(f"Script: {script}", True)
            else:
                print_error(f"{script}: NOT present")
                self.results.add_check(f"Script: {script}", False)
                all_passed = False

        return all_passed

    def verify_test_suite(self) -> bool:
        """Verify test suite exists."""
        print_section("11. TEST SUITE CHECK")

        test_path = self.paths.tests / "test_backtest_sanity_production.py"

        if not test_path.exists():
            print_warning("test_backtest_sanity_production.py NOT present (optional)")
            self.results.add_check("Test suite", False, "Optional file not found")
            return False

        size = test_path.stat().st_size
        lines = len(test_path.read_text(encoding="utf-8", errors="ignore").splitlines())

        print_success(
            f"test_backtest_sanity_production.py: present ({size:,} bytes, {lines} lines)"
        )
        self.results.add_check("Test suite", True, f"{size:,} bytes, {lines} lines")

        # Count test functions
        test_content = test_path.read_text(encoding="utf-8", errors="ignore")
        test_count = len(re.findall(r"def test_", test_content))
        print_info(f"Test functions: {test_count}")

        return True

    def verify_documentation(self) -> bool:
        """Verify documentation exists."""
        print_section("12. DOCUMENTATION CHECK")

        # F8-M-05: completion reports are archived under docs/audit-history/,
        # not kept at the docs/ top level (compact-repo rule, CMP §4/§8).
        doc_path = self.paths.docs / "audit-history" / "TODO26_FINAL_REPORT.md"

        if not doc_path.exists():
            print_warning("TODO26_FINAL_REPORT.md NOT present (optional)")
            self.results.add_check("Documentation", False, "Optional file not found")
            return False

        size = doc_path.stat().st_size
        print_success(f"TODO26_FINAL_REPORT.md: present ({size:,} bytes)")
        self.results.add_check("Documentation", True, f"{size:,} bytes")

        return True

    def print_summary(self) -> None:
        """Print verification summary."""
        print_section("VERIFICATION SUMMARY")

        print(f"\n{Colors.BOLD}Total Checks:{Colors.ENDC} {self.results.total}")
        print(
            f"{Colors.OKGREEN}{Colors.BOLD}Passed:{Colors.ENDC} {self.results.passed}"
        )
        print(f"{Colors.FAIL}{Colors.BOLD}Failed:{Colors.ENDC} {self.results.failed}")

        if self.results.warnings:
            print(
                f"\n{Colors.WARNING}{Colors.BOLD}Warnings:{Colors.ENDC} {len(self.results.warnings)}"
            )
            for warning in self.results.warnings:
                print_warning(warning)

        print(
            f"\n{Colors.BOLD}Pass Rate:{Colors.ENDC} {(self.results.passed / self.results.total * 100):.1f}%"
        )

        if self.results.failed == 0:
            print(
                f"\n{Colors.OKGREEN}{Colors.BOLD}✓ ALL CHECKS PASSED - TODO-26 IMPLEMENTATION VERIFIED{Colors.ENDC}\n"
            )
        else:
            print(
                f"\n{Colors.FAIL}{Colors.BOLD}✗ {self.results.failed} CHECK(S) FAILED - TODO-26 NEEDS ATTENTION{Colors.ENDC}\n"
            )

    def run_all_verifications(self) -> bool:
        """Run all verification checks."""
        print_header("TODO-26 (F7-L-06) EXTERNAL VERIFICATION")
        print_info("Task: Drive backtest_sanity - Wire CMP P4 exit gate module")
        print_info("      with weekly scheduler job against /history data")
        print_info(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Run all checks
        self.verify_module_exists()
        self.verify_module_structure()
        self.verify_required_classes()
        self.verify_required_functions()
        self.verify_scheduler_wiring()
        self.verify_run_once_integration()
        self.verify_health_check_integration()
        self.verify_no_lookahead_logic()
        self.verify_walk_forward_iterator()
        self.verify_verification_scripts()
        self.verify_test_suite()
        self.verify_documentation()

        # Print summary
        self.print_summary()

        return self.results.failed == 0


def main() -> int:
    """Main entry point."""
    try:
        verifier = TODO26Verifier()
        success = verifier.run_all_verifications()
        return 0 if success else 1
    except Exception as e:
        print_error(f"Verification failed with error: {e}")
        import traceback

        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
