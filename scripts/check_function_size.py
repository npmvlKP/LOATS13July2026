#!/usr/bin/env python3
"""Check function size Python files ensure function exceeds 100 lines."""

import ast
import sys
from pathlib import Path


def check_function_size() -> int:
    """Check function size all Python files src/ directory.
    Phase-00: max_lines set 200 (temporary).
    4.1 target ≤100 LOC; large functions (_initialize_database,
    calculate_indicators) refactored Phase 01-02.
    """
    max_lines = 200
    exit_code = 0
    src = Path(__file__).parent.parent / "src"
    path = src.rglob("*.py")
    try:
        for file in path:
            content = file.read_text(encoding="utf-8")
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    start = node.lineno
                    end = node.end_lineno
                    if end - start > max_lines:
                        print(
                            f"{file}:{start} Function {node.name} large ({end - start} lines)"
                        )
                        exit_code = 1
    except Exception as e:
        print(f"Error processing {file}: {e}")
        exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(check_function_size())
