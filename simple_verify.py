#!/usr/bin/env python3
"""
Simple SQL Injection Verification Script
"""

import re
import sys

def main():
    file_path = 'src/loats/database.py'

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check for SQL injection patterns
    patterns = {
        'f-string SQL': r'cursor\.execute\(f["\'`]',
        '%s formatting': r'cursor\.execute\(.*\%s',
        'string concatenation': r'cursor\.execute\(.*\+.*',
        '.format() method': r'cursor\.execute\(.*format\(.*\)',
        'string interpolation': r'cursor\.execute\(.*\.\.\.'
    }

    print("SQL INJECTION PATTERN VERIFICATION")
    print("=" * 50)

    vulnerabilities_found = False
    for name, pattern in patterns.items():
        matches = re.findall(pattern, content)
        count = len(matches)
        print(f"{name}: {count}")
        if count > 0:
            vulnerabilities_found = True

    # Check for proper parameterized queries
    param_queries = len(re.findall(r'cursor\.execute\(.*\?.*\)', content))
    print(f"Parameterized queries: {param_queries}")

    print("\n" + "=" * 50)
    if vulnerabilities_found:
        print("RESULT: POTENTIAL SQL INJECTION VULNERABILITIES FOUND")
        return 1
    else:
        print("RESULT: NO SQL INJECTION VULNERABILITIES FOUND")
        print("The database implementation is secure")
        return 0

if __name__ == "__main__":
    sys.exit(main())
