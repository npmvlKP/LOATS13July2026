#!/usr/bin/env python3
"""
Validation script for aiosqlite dependency fix.

This script validates that:
1. aiosqlite module is properly installed
2. The module can be imported without errors
3. All connection pool tests pass
4. The dependency is properly declared in project files
"""

import importlib
import subprocess
import sys


def validate_aiosqlite_import():
    """Validate that aiosqlite can be imported successfully."""
    print("1. Validating aiosqlite import...")
    try:
        aiosqlite = importlib.import_module("aiosqlite")
        version = aiosqlite.__version__
        print("   [OK] aiosqlite imported successfully")
        print(f"   [OK] Version: {version}")
        return True
    except ImportError as e:
        print(f"   [FAIL] Failed to import aiosqlite: {e}")
        return False
    except Exception as e:
        print(f"   [FAIL] Unexpected error: {e}")
        return False


def validate_test_execution():
    """Validate that connection pool tests pass."""
    print("\n2. Validating connection pool tests...")
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_connection_pool_coverage.py",
                "-v",
                "--tb=short",
            ],
            capture_output=True,
            text=True,
            cwd=".",
        )

        if result.returncode == 0:
            # Count passed tests
            passed_count = result.stdout.count(" PASSED")
            print(f"   [OK] All {passed_count} connection pool tests passed")
            return True
        else:
            print(f"   [FAIL] Tests failed with return code: {result.returncode}")
            print("   Error output:")
            print(result.stderr)
            return False
    except Exception as e:
        print(f"   [FAIL] Failed to run tests: {e}")
        return False


def validate_dependency_declaration():
    """Validate that aiosqlite is properly declared in project files."""
    print("\n3. Validating dependency declarations...")

    # Check pyproject.toml
    try:
        with open("pyproject.toml", "r") as f:
            pyproject_content = f.read()
            if "aiosqlite>=0.21.0" in pyproject_content:
                print("   [OK] aiosqlite declared in pyproject.toml")
            else:
                print("   [FAIL] aiosqlite not found in pyproject.toml")
                return False
    except FileNotFoundError:
        print("   [FAIL] pyproject.toml not found")
        return False
    except Exception as e:
        print(f"   [FAIL] Error reading pyproject.toml: {e}")
        return False

    # Check requirements-core.txt
    try:
        with open("requirements-core.txt", "r") as f:
            requirements_content = f.read()
            if "aiosqlite>=0.21.0" in requirements_content:
                print("   [OK] aiosqlite declared in requirements-core.txt")
            else:
                print("   [FAIL] aiosqlite not found in requirements-core.txt")
                return False
    except FileNotFoundError:
        print("   [FAIL] requirements-core.txt not found")
        return False
    except Exception as e:
        print(f"   [FAIL] Error reading requirements-core.txt: {e}")
        return False

    return True


def main():
    """Main validation function."""
    print("=" * 60)
    print("AIOSQLITE DEPENDENCY FIX VALIDATION")
    print("=" * 60)

    all_valid = True

    # Run all validations
    import_valid = validate_aiosqlite_import()
    test_valid = validate_test_execution()
    deps_valid = validate_dependency_declaration()

    # Check overall status
    all_valid = import_valid and test_valid and deps_valid

    print("\n" + "=" * 60)
    if all_valid:
        print("[SUCCESS] ALL VALIDATIONS PASSED - aiosqlite fix is complete")
        print("=" * 60)
        return 0
    else:
        print("[FAILURE] SOME VALIDATIONS FAILED - please review")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
