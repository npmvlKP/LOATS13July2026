#!/usr/bin/env python3
"""Syntax check all Python files in src/ directory."""

import ast
import sys
from pathlib import Path


def check_file(filepath: Path) -> bool:
    """Check syntax of a single Python file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        ast.parse(content)
        print(f"[OK] {filepath}")
        return True
    except SyntaxError as e:
        print(f"[FAIL] {filepath}: {e.msg} (line {e.lineno})")
        lines = content.split('\n')
        start = max(0, e.lineno - 3)
        end = min(len(lines), e.lineno + 2)
        for i in range(start, end):
            marker = ">>>" if i == e.lineno - 1 else "   "
            print(f"  {marker} {i + 1}: {lines[i]}")
        return False


def main():
    """Check all Python files in src/ directory."""
    src_dir = Path("src/loats")
    results = []
    
    for py_file in src_dir.rglob("*.py"):
        results.append(check_file(py_file))
    
    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} files passed syntax check")
    
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())