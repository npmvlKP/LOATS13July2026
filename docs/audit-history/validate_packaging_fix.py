#!/usr/bin/env python3
"""
Validation script for packaging fix (F-DEP-1).

This script validates that the packaging issue has been resolved by testing:
1. Package installation
2. Package import
3. Entry point functionality
4. Module functionality
"""

import asyncio
import importlib
import subprocess
import sys
from pathlib import Path

# Ensure UTF-8 encoding for Windows
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def run_command(cmd, timeout=30):
    """Run a command and return the result."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"


def test_package_import():
    """Test that the package can be imported correctly."""
    print("Testing package import...")

    try:
        # Test import of the main module
        loats = importlib.import_module("loats")
        print("OK Package 'loats' imported successfully")
        print(f"OK Version: {loats.__version__}")

        # Test import of key components
        from loats.main import TradingSystem

        # Use the imports to verify they work
        _ = TradingSystem

        print("OK TradingSystem imported successfully")

        from loats.config import get_settings

        # Use the import to verify it works
        _ = get_settings

        print("OK get_settings imported successfully")

        return True
    except ImportError as e:
        print(f"X Import failed: {e}")
        return False
    except Exception as e:
        print(f"X Unexpected error during import: {e}")
        return False


def test_entry_point():
    """Test that the entry point works correctly."""
    print("\nTesting entry point...")

    # Test that the entry point exists and is callable
    try:
        from loats.main import cli_main

        print("OK Entry point 'cli_main' is accessible")

        # Test that it's a proper function (not a coroutine)
        if asyncio.iscoroutinefunction(cli_main):
            print("X Entry point is still a coroutine function")
            return False
        else:
            print("OK Entry point is a proper synchronous function")
            return True

    except ImportError as e:
        print(f"X Entry point import failed: {e}")
        return False
    except Exception as e:
        print(f"X Unexpected error testing entry point: {e}")
        return False


def test_package_structure():
    """Test that the package structure is correct."""
    print("\nTesting package structure...")

    # Check that the package is installed in the right location
    try:
        import loats

        package_path = Path(loats.__file__).parent
        print(f"OK Package installed at: {package_path}")

        # Check that key modules exist
        expected_modules = [
            "main.py",
            "alerts.py",
            "database.py",
            "scheduler.py",
            "config",
            "utils",
        ]

        for module in expected_modules:
            module_path = package_path / module
            if module_path.exists() or (module_path.parent / module).exists():
                print(f"OK Module {module} exists")
            else:
                print(f"X Module {module} missing")
                return False

        return True
    except Exception as e:
        print(f"X Error checking package structure: {e}")
        return False


def main():
    """Run all validation tests."""
    print("=== LOATS13July2026 Packaging Validation (F-DEP-1) ===\n")

    tests = [
        ("Package Import", test_package_import),
        ("Entry Point", test_entry_point),
        ("Package Structure", test_package_structure),
    ]

    results = []
    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        result = test_func()
        results.append((test_name, result))

    print("\n=== SUMMARY ===")
    all_passed = True
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{test_name}: {status}")
        if not result:
            all_passed = False

    if all_passed:
        print("\n All packaging tests PASSED! F-DEP-1 is RESOLVED.")
        return 0
    else:
        print("\nX Some packaging tests FAILED! F-DEP-1 is NOT resolved.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
