#!/usr/bin/env python3
"""Comprehensive Python verification script for TODO-20 completion.

This script provides user-external verification of the successful TODO-20 implementation:
- Kill the audit PYTEST_CURRENT_TEST bypass
- Fix tests to exercise the REAL dual-write path
- Verify git grep PYTEST_CURRENT_TEST -- src/ returns empty
- Test asserts both SQLite row AND JSONL line + digest for a write

Usage:
    python scripts/verify_todo20_implementation.py
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd, cwd=None):
    """Run a command and return output."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result.stdout, result.stderr, result.returncode

def check_git_grep_empty():
    """Verify git grep PYTEST_CURRENT_TEST -- src/ returns empty."""
    print("=" * 70)
    print("CHECK 1: Verify git grep PYTEST_CURRENT_TEST -- src/ returns empty")
    print("=" * 70)

    stdout, stderr, exit_code = run_command(
        ["git", "grep", "PYTEST_CURRENT_TEST", "--", "src/"]
    )

    if exit_code == 1 and not stdout:
        print("✓ PASS: No PYTEST_CURRENT_TEST found in src/")
        return True
    else:
        print("✗ FAIL: PYTEST_CURRENT_TEST still exists in src/:")
        print(stdout)
        return False

def check_database_py_no_bypass():
    """Verify database.py has no PYTEST_CURRENT_TEST bypass."""
    print("\n" + "=" * 70)
    print("CHECK 2: Verify database.py has no PYTEST_CURRENT_TEST bypass")
    print("=" * 70)

    stdout, stderr, exit_code = run_command(
        ["git", "grep", "PYTEST_CURRENT_TEST", "--", "src/loats/database.py"]
    )

    if exit_code == 1 and not stdout:
        print("✓ PASS: database.py has no PYTEST_CURRENT_TEST bypass")
        return True
    else:
        print("✗ FAIL: database.py still has PYTEST_CURRENT_TEST:")
        print(stdout)
        return False

def check_test_file_exists():
    """Verify test_audit_dual_write.py exists."""
    print("\n" + "=" * 70)
    print("CHECK 3: Verify test_audit_dual_write.py exists")
    print("=" * 70)

    test_file = Path("tests/test_audit_dual_write.py")
    if test_file.exists():
        print(f"✓ PASS: {test_file} exists")
        print(f"  File size: {test_file.stat().st_size} bytes")
        return True
    else:
        print(f"✗ FAIL: {test_file} does not exist")
        return False

def check_test_content():
    """Verify test file contains required assertions."""
    print("\n" + "=" * 70)
    print("CHECK 4: Verify test contains dual-write assertions")
    print("=" * 70)

    test_file = Path("tests/test_audit_dual_write.py")
    if not test_file.exists():
        print("✗ FAIL: Test file does not exist")
        return False

    content = test_file.read_text(encoding="utf-8")

    # Check for key assertions
    required_checks = [
        ("SQLite row exists", "SQLite audit row must exist"),
        ("JSONL line exists", "JSONL audit file must exist"),
        ("SHA-256 digest match", "SHA-256 digest must match SQLite row digest"),
        ("tmp_path fixture", "def test_audit_dual_write_with_injectable_path(tmp_path):"),
        ("canonical serialization", "canonical serialization"),
    ]

    all_passed = True
    for check_name, check_pattern in required_checks:
        if check_pattern in content:
            print(f"  ✓ Contains: {check_name}")
        else:
            print(f"  ✗ Missing: {check_name}")
            all_passed = False

    if all_passed:
        print("✓ PASS: All required dual-write assertions present")
        return True
    else:
        print("✗ FAIL: Some assertions missing")
        return False

def check_health_check_exists():
    """Verify HC-22 health check exists."""
    print("\n" + "=" * 70)
    print("CHECK 5: Verify HC-22 health check exists")
    print("=" * 70)

    health_check_file = Path("scripts/fr7_health_check.py")
    if not health_check_file.exists():
        print(f"✗ FAIL: {health_check_file} does not exist")
        return False

    content = health_check_file.read_text(encoding="utf-8")

    if '"HC-22"' in content:
        print("✓ PASS: HC-22 health check defined")
        # Extract HC-22 definition
        hc22_start = content.find('"HC-22"')
        hc22_end = content.find('},', hc22_start) + 2
        hc22_def = content[hc22_start:hc22_end]
        print(f"  Definition:\n{hc22_def}")
        return True
    else:
        print("✗ FAIL: HC-22 health check not found")
        return False

def run_hc22_health_check():
    """Run HC-22 health check."""
    print("\n" + "=" * 70)
    print("CHECK 6: Run HC-22 health check")
    print("=" * 70)

    stdout, stderr, exit_code = run_command(
        ["uv", "run", "python", "scripts/fr7_health_check.py", "--only", "HC-22"]
    )

    print(stdout)
    if stderr:
        print("STDERR:", stderr)

    if exit_code == 0:
        print("✓ PASS: HC-22 health check passed")
        return True
    else:
        print("✗ FAIL: HC-22 health check failed")
        return False

def verify_pytest_can_run_test():
    """Verify pytest can run the dual-write test."""
    print("\n" + "=" * 70)
    print("CHECK 7: Verify pytest can run test_audit_dual_write.py")
    print("=" * 70)

    stdout, stderr, exit_code = run_command(
        ["uv", "run", "pytest", "tests/test_audit_dual_write.py", "-v"]
    )

    if exit_code == 0:
        print("✓ PASS: All dual-write tests passed")
        print(f"  Test output:\n{stdout}")
        return True
    else:
        print("✗ FAIL: Some tests failed")
        print(f"  STDOUT:\n{stdout}")
        print(f"  STDERR:\n{stderr}")
        return False

def main():
    """Run all verification checks."""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 10 + "TODO-20 IMPLEMENTATION VERIFICATION" + " " * 21 + "║")
    print("╚" + "=" * 68 + "╝")
    print()

    results = []

    # Run all checks
    results.append(("git grep PYTEST_CURRENT_TEST -- src/ empty", check_git_grep_empty()))
    results.append(("database.py no bypass", check_database_py_no_bypass()))
    results.append(("test_audit_dual_write.py exists", check_test_file_exists()))
    results.append(("test dual-write assertions", check_test_content()))
    results.append(("HC-22 health check defined", check_health_check_exists()))
    results.append(("HC-22 health check passes", run_hc22_health_check()))
    results.append(("pytest runs dual-write tests", verify_pytest_can_run_test()))

    # Summary
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for check_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {check_name}")

    print(f"\nTotal: {passed}/{total} checks passed")

    if passed == total:
        print("\n" + "╔" + "=" * 68 + "╗")
        print("║" + " " * 18 + "ALL CHECKS PASSED - TODO-20 COMPLETE" + " " * 19 + "║")
        print("╚" + "=" * 68 + "╝")
        return 0
    else:
        print("\n" + "╔" + "=" * 68 + "╗")
        print("║" + " " * 16 + "SOME CHECKS FAILED - REVIEW REQUIRED" + " " * 19 + "║")
        print("╚" + "=" * 68 + "╝")
        return 1

if __name__ == "__main__":
    sys.exit(main())
