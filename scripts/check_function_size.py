#!/usr/bin/env python3
"""Check function size across Python files ensure functions not exceed maximum line count."""

import ast
import sys
from pathlib import Path


def check_file_function_size(file_path: Path, max_lines: int) -> list[str]:
    """Check all function sizes in a single file.

    Args:
        file_path: Path to the Python file to check
        max_lines: Maximum allowed function size in lines

    Returns:
        List of violation messages for functions exceeding max_lines
    """
    violations: list[str] = []
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                start = node.lineno
                end = getattr(node, "end_lineno", None)
                if start is None or end is None:
                    continue
                func_size = end - start + 1
                if func_size > max_lines:
                    violations.append(
                        f"{file_path}:{start} Function {node.name} too large ({func_size} lines)"
                    )
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
    return violations


def check_function_size(max_lines: int = 200) -> int:
    """Check function sizes across all Python files in the project.

    Phase-00: max_lines set to 200 (temporary).
    Target ≤100 LOC after Phase 01-02 refactoring.

    Returns:
        Exit code (0 for pass, 1 for fail)
    """
    exit_code = 0
    src_path = Path(__file__).parent.parent / "src"
    for file_path in src_path.rglob("*.py"):
        violations = check_file_function_size(file_path, max_lines)
        for violation in violations:
            print(violation)
            exit_code = 1
    return exit_code


def main() -> None:
    """CLI entry point."""
    sys.exit(check_function_size())


if __name__ == "__main__":
    main()
