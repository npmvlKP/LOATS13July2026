#!/usr/bin/env python3
"""External verification script for TODO-24 (F7-L-04) exit semantics.

Validates:
1. Exit code 0 on success
2. Exit code 1 on all failure paths
3. No warning path can fall through to exit 0
4. Proper error message propagation
5. Unit test coverage for exit codes

Exit codes:
    0: All verification passed
    1: One or more verifications failed
"""

import re
import shutil
import subprocess
import sys
import traceback
from pathlib import Path


def get_project_root() -> Path:
    """Get project root directory robustly."""
    try:
        script_file = Path(__file__).resolve()
        if "scripts" in script_file.parts:
            idx = script_file.parts.index("scripts")
            return Path(*script_file.parts[:idx])
    except Exception:
        pass

    cwd = Path.cwd()
    if (cwd / "pyproject.toml").exists() and (cwd / "scripts").is_dir():
        return cwd

    for parent in list(cwd.parents):
        if (parent / "pyproject.toml").exists() and (parent / "scripts").is_dir():
            return parent

    return cwd


PROJECT_ROOT = get_project_root()
COVERAGE_SCRIPT = PROJECT_ROOT / "scripts" / "check_per_module_coverage.py"
TEST_FILE = PROJECT_ROOT / "tests" / "test_check_per_module_coverage.py"
HEALTH_CHECK_FILE = PROJECT_ROOT / "scripts" / "fr7_health_check.py"


def run_command(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """Run command and return exit code, stdout, stderr."""
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=cwd or PROJECT_ROOT
    )
    return result.returncode, result.stdout, result.stderr


def verify_exit_semantics_source() -> bool:
    """Verify source code has correct exit semantics."""
    try:
        if not COVERAGE_SCRIPT.is_file():
            print(f"X FAILED: Script not found at {COVERAGE_SCRIPT}")
            return False

        content = COVERAGE_SCRIPT.read_text(encoding="utf-8")
        lines = content.splitlines()

        exit_lines = []
        for i, raw_line in enumerate(lines, 1):
            line = raw_line.strip()
            if "sys.exit" in line and not line.startswith("#"):
                exit_lines.append((i, line))

        print("\n=== EXIT SEMANTICS SOURCE VERIFICATION ===")
        print(f"Found {len(exit_lines)} sys.exit() calls:")

        exit_0_count = 0
        exit_1_count = 0

        for line_num, line in exit_lines:
            print(f"  Line {line_num}: {line}")
            if "sys.exit(0)" in line:
                exit_0_count += 1
            elif "sys.exit(1)" in line:
                exit_1_count += 1

        if exit_0_count != 1:
            print(f"\nX FAILED: Expected exactly 1 sys.exit(0), found {exit_0_count}")
            return False

        if exit_1_count < 4:
            print(
                f"\nX FAILED: Expected at least 4 sys.exit(1) calls, found {exit_1_count}"
            )
            return False

        last_line_num, last_line_text = exit_lines[-1]
        if last_line_num != 177 or "sys.exit(0)" not in last_line_text:
            print(
                f"\nX FAILED: Final exit should be sys.exit(0) at line 177, got line {last_line_num}: {last_line_text}"
            )
            return False

        print("\n  Exit semantics verified:")
        print("  - sys.exit(0): 1 call (success path only)")
        print(f"  - sys.exit(1): {exit_1_count} calls (all error paths)")
        print("  - Final exit: sys.exit(0) at line 177")

        return True

    except Exception:
        print("\nX FAILED: verify_exit_semantics_source() crashed:")
        traceback.print_exc()
        return False


def verify_unit_tests_exist() -> bool:
    """Verify unit tests for exit codes exist."""
    try:
        print("\n=== UNIT TEST VERIFICATION ===")

        if not TEST_FILE.is_file():
            print(f"X FAILED: Unit test file not found at {TEST_FILE}")
            return False

        content = TEST_FILE.read_text(encoding="utf-8")

        required_tests = [
            "test_exit_0_all_modules_pass_threshold",
            "test_exit_1_module_below_threshold",
            "test_exit_1_missing_coverage_file",
            "test_exit_1_invalid_json",
            "test_exit_1_no_module_data",
            "test_no_warning_fallthrough_to_exit_0",
        ]

        missing_tests = [t for t in required_tests if f"def {t}" not in content]

        if missing_tests:
            print("X FAILED: Missing required unit tests:")
            for test in missing_tests:
                print(f"  - {test}")
            return False

        print("  All required unit tests present:")
        for test in required_tests:
            print(f"  - {test}")

        return True

    except Exception:
        print("\nX FAILED: verify_unit_tests_exist() crashed:")
        traceback.print_exc()
        return False


def run_unit_tests() -> bool:
    """Run unit tests and verify they pass."""
    try:
        print("\n=== RUNNING UNIT TESTS ===")

        if shutil.which("uv"):
            cmd = ["uv", "run", "pytest", str(TEST_FILE), "-v"]
        else:
            cmd = [sys.executable, "-m", "pytest", str(TEST_FILE), "-v"]

        exit_code, stdout, stderr = run_command(cmd)

        print(stdout)
        if stderr:
            print("STDERR:", stderr)

        if exit_code != 0:
            print(f"\nX FAILED: Unit tests failed with exit code {exit_code}")
            return False

        if "passed" not in stdout.lower():
            print("\nX FAILED: Tests did not report PASSED status")
            return False

        print("\n  All unit tests passed")
        return True

    except Exception:
        print("\nX FAILED: run_unit_tests() crashed:")
        traceback.print_exc()
        return False


def verify_integration_with_health_check() -> bool:
    """Verify integration with the FR7 health-check catalogue (G02)."""
    try:
        print("\n=== HEALTH CHECK INTEGRATION VERIFICATION ===")

        if not HEALTH_CHECK_FILE.is_file():
            print("X FAILED: Health check script not found")
            return False

        content = HEALTH_CHECK_FILE.read_text(encoding="utf-8")

        # Accept both legacy (HC-13) and new grouped catalogue (G02):
        # both must reference check_per_module_coverage.py with TODO-15.
        has_gate = ("HC-13" in content) or ('id="G02"' in content)
        if not has_gate or "check_per_module_coverage.py" not in content:
            print(
                "X FAILED: health check does not reference check_per_module_coverage.py (G02/HC-13)"
            )
            return False

        if "TODO-15" not in content:
            print("X FAILED: coverage gate missing TODO-15 reference")
            return False

        print("  Coverage gate (G02, formerly HC-13) properly configured:")
        print("  - References check_per_module_coverage.py")
        print("  - Linked to TODO-15 (folded from TODO-24)")

        return True

    except Exception:
        print("\nX FAILED: verify_integration_with_health_check() crashed:")
        traceback.print_exc()
        return False


def verify_no_fallthrough_paths() -> bool:
    """Verify no warning path can fall through to exit 0."""
    try:
        print("\n=== FALLTHROUGH PATH ANALYSIS ===")

        if not COVERAGE_SCRIPT.is_file():
            print("X FAILED: Script not found")
            return False

        content = COVERAGE_SCRIPT.read_text(encoding="utf-8")

        all_exit_calls = list(re.finditer(r"sys\.exit\((\d+)\)", content))

        if len(all_exit_calls) < 5:
            print(
                f"X FAILED: Expected at least 5 sys.exit calls, found {len(all_exit_calls)}"
            )
            return False

        last_exit = all_exit_calls[-1]
        if last_exit.group(1) != "0":
            print(
                f"X FAILED: Last sys.exit is not sys.exit(0), it's sys.exit({last_exit.group(1)})"
            )
            return False

        exit_0_positions = [
            i for i, call in enumerate(all_exit_calls) if call.group(1) == "0"
        ]
        exit_1_positions = [
            i for i, call in enumerate(all_exit_calls) if call.group(1) == "1"
        ]

        if exit_1_positions and exit_0_positions:
            if max(exit_1_positions) > min(exit_0_positions):
                print("X FAILED: Exit(1) found after exit(0) - fallthrough risk")
                return False

        print("  No fallthrough paths detected:")
        print(f"  - Total sys.exit calls: {len(all_exit_calls)}")
        print(f"  - sys.exit(1): {len(exit_1_positions)} calls (all error paths)")
        print(f"  - sys.exit(0): {len(exit_0_positions)} call (success path)")
        print("  - All error exits occur before success exit")
        print(f"  - Final exit is sys.exit(0) (position {len(all_exit_calls) - 1})")

        return True

    except Exception:
        print("\nX FAILED: verify_no_fallthrough_paths() crashed:")
        traceback.print_exc()
        return False


def verify_copyright_and_docs() -> bool:
    """Verify script has proper documentation."""
    try:
        print("\n=== DOCUMENTATION VERIFICATION ===")

        if not COVERAGE_SCRIPT.is_file():
            print("X FAILED: Script not found")
            return False

        content = COVERAGE_SCRIPT.read_text(encoding="utf-8")

        if '"""' not in content[:200]:
            print("X FAILED: Script missing docstring")
            return False

        doc_match = re.search(r'"""(.+?)"""', content[:500], re.DOTALL)
        if not doc_match:
            print("X FAILED: Could not extract docstring")
            return False

        docstring = doc_match.group(1).lower()

        required_keywords = ["coverage", "floor map", "80%", "threshold"]
        missing_keywords = [kw for kw in required_keywords if kw not in docstring]

        if missing_keywords:
            print(f"X FAILED: Docstring missing keywords: {missing_keywords}")
            return False

        print("  Documentation verified:")
        print("  - Script has docstring")
        print(f"  - Contains required keywords: {', '.join(required_keywords)}")

        return True

    except Exception:
        print("\nX FAILED: verify_copyright_and_docs() crashed:")
        traceback.print_exc()
        return False


def main() -> int:
    """Main verification routine."""
    print("=" * 70)
    print("TODO-24 (F7-L-04) Exit Semantics Verification")
    print("=" * 70)

    results = [
        ("Exit Semantics Source", verify_exit_semantics_source()),
        ("Unit Tests Exist", verify_unit_tests_exist()),
        ("Unit Tests Pass", run_unit_tests()),
        ("Health Check Integration", verify_integration_with_health_check()),
        ("No Fallthrough Paths", verify_no_fallthrough_paths()),
        ("Documentation", verify_copyright_and_docs()),
    ]

    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")

    print(f"\nTotal: {passed}/{total} passed")

    if passed == total:
        print("\nTODO-24 VERIFICATION COMPLETE: All checks passed")
        print("Exit semantics verified. Unit tests added. Integrated with TODO-15.")
        return 0
    else:
        print(f"\nTODO-24 VERIFICATION FAILED: {total - passed} check(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
