#!/usr/bin/env python3
"""Check function size in Python files to ensure no function exceeds 100 lines."""

import ast
import sys
from pathlib import Path


def check_function_size() -> int:
    """Check function size in all Python files in src/ directory."""
    max_lines = 100
    exit_code = 0

    for path in Path("src/").rglob("*.py"):
        try:
            content = path.read_text(encoding="utf-8")
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    start = node.lineno
                    end = node.end_lineno
                    if end - start > max_lines:
                        print(
                            f"{path}:{start} Function {node.name} too large ({end - start} lines)"
                        )
                        exit_code = 1
        except Exception as e:
            print(f"Error processing {path}: {e}")
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(check_function_size())
