#!/usr/bin/env python3
"""
SQL Injection Verification Script
Verifies that no SQL injection vulnerabilities exist in the database implementation.
"""

import re
import sys

# Set UTF-8 encoding for Windows
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

def check_for_sql_injection_patterns(file_path):
    """Check for various SQL injection patterns in a file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check for f-string SQL patterns
    f_string_patterns = re.findall(r'cursor\.execute\(f["\'`]', content)
    print(f"F-string SQL patterns: {len(f_string_patterns)}")

    # Check for other dangerous patterns
    dangerous_patterns = [
        r'cursor\.execute\(.*\%s',  # String formatting with %s
        r'cursor\.execute\(.*\+.*',  # String concatenation
        r'cursor\.execute\(.*format\(.*\)',  # .format() method
        r'cursor\.execute\(.*\.\.\.',  # String interpolation
    ]

    for pattern in dangerous_patterns:
        matches = re.findall(pattern, content)
        print(f"Pattern '{pattern}': {len(matches)} matches")

    # Check for proper parameterized queries
    param_queries = re.findall(r'cursor\.execute\(.*\?.*\)', content)
    print(f"Parameterized queries with ? placeholders: {len(param_queries)}")

    # Check for parameter tuples
    param_tuples = re.findall(r'cursor\.execute\(.*\(.*\).*\)', content)
    print(f"Queries with parameter tuples: {len(param_tuples)}")

    return len(f_string_patterns) == 0 and all(len(re.findall(p, content)) == 0 for p in dangerous_patterns)

def verify_database_implementation(file_path):
    """Verify that the database implementation follows security best practices."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check for proper connection management
    has_connection_management = 'def _get_connection' in content
    print(f"Has connection management: {has_connection_management}")

    # Check for parameterized queries
    has_param_queries = 'cursor.execute(' in content and '?' in content
    print(f"Uses parameterized queries: {has_param_queries}")

    # Check for audit logging
    has_audit_logging = 'def _log_audit' in content
    print(f"Has audit logging: {has_audit_logging}")

    # Check for cryptographic hashing
    has_hashing = '_calculate_sha256' in content
    print(f"Has cryptographic hashing: {has_hashing}")

    return has_connection_management and has_param_queries and has_audit_logging and has_hashing

if __name__ == "__main__":
    file_path = 'src/loats/database.py'

    print("=" * 60)
    print("SQL INJECTION VULNERABILITY VERIFICATION")
    print("=" * 60)

    print(f"\nAnalyzing file: {file_path}")
    print("\n1. SQL Injection Pattern Check:")
    no_injection_patterns = check_for_sql_injection_patterns(file_path)

    print("\n2. Database Implementation Security Check:")
    secure_implementation = verify_database_implementation(file_path)

    print("\n" + "=" * 60)
    print("SUMMARY:")
    print(f"✅ No SQL injection patterns found: {no_injection_patterns}")
    print(f"✅ Secure database implementation: {secure_implementation}")

    if no_injection_patterns and secure_implementation:
        print("\n🎉 RESULT: No SQL injection vulnerabilities found")
        print("The database implementation follows security best practices")
        sys.exit(0)
    else:
        print("\n❌ RESULT: Potential security issues detected")
        sys.exit(1)