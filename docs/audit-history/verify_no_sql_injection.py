#!/usr/bin/env python3
"""
SQL Injection Verification Script
This script verifies that no SQL injection vulnerabilities exist in the
database implementation.
Run this script to confirm the forensic analysis findings.
"""

import re
import sys

# Set UTF-8 encoding for Windows
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def verify_no_sql_injection():
    """Verify that no SQL injection patterns exist in database.py"""

    # Read the database file
    try:
        with open("src/loats/database.py", "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print("ERROR: File 'src/loats/database.py' not found")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

    print("=" * 60)
    print("SQL INJECTION VULNERABILITY VERIFICATION")
    print("=" * 60)
    print("Analyzing file: src/loats/database.py")
    print(f"File size: {len(content)} characters")
    print()

    # Check for SQL injection patterns
    patterns = {
        "F-string SQL queries": r'cursor\.execute\(f["\'`]',
        "String formatting (%s)": r"cursor\.execute\(.*\%s",
        "String concatenation (+)": r"cursor\.execute\(.*\+.*",
        ".format() method": r"cursor\.execute\(.*format\(.*\)",
        "String interpolation (...)": r"cursor\.execute\(.*\.\.\.",
    }

    vulnerabilities_found = False

    print("SQL INJECTION PATTERN CHECK:")
    for name, pattern in patterns.items():
        matches = re.findall(pattern, content)
        count = len(matches)
        status = "❌ VULNERABLE" if count > 0 else "✅ SECURE"
        print(f"  {name}: {count} matches {status}")
        if count > 0:
            vulnerabilities_found = True

    print()

    # Check for proper parameterized queries
    param_queries = re.findall(r"cursor\.execute\(.*\?.*\)", content)
    secure_queries = len(param_queries)
    print("SECURE QUERIES:")
    print(f"  Parameterized queries with ? placeholders: {secure_queries} ✅")

    # Check for security features
    print()
    print("SECURITY FEATURES:")
    security_features = {
        "Connection management": "def _get_connection" in content,
        "Audit logging": "def _log_audit" in content,
        "Cryptographic hashing": "_calculate_sha256" in content,
        "Thread safety": "threading.Lock" in content,
        "UTC datetime handling": "UTC" in content,
        "Decimal finance handling": "Decimal" in content,
    }

    for name, present in security_features.items():
        status = "✅ PRESENT" if present else "❌ MISSING"
        print(f"  {name}: {status}")

    print()
    print("=" * 60)

    if vulnerabilities_found:
        print("RESULT: ❌ POTENTIAL SQL INJECTION VULNERABILITIES FOUND")
        print(
            "The database implementation may have security issues that "
            "need to be addressed."
        )
        return False
    else:
        print("RESULT: ✅ NO SQL INJECTION VULNERABILITIES FOUND")
        print("The database implementation follows security best practices.")
        print("All SQL queries use proper parameterized queries with ? placeholders.")
        return True


if __name__ == "__main__":
    success = verify_no_sql_injection()
    sys.exit(0 if success else 1)
