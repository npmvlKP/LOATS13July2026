#!/usr/bin/env python3
"""Fix all test imports from src.loats to loats."""

import re
from pathlib import Path


def fix_imports_in_file(filepath: Path) -> None:
    """Fix imports in a single file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Replace from src.loats with from loats
        original_content = content
        content = re.sub(r"from src\.loats", "from loats", content)

        # Also replace import src.loats with import loats
        content = re.sub(r"import src\.loats", "import loats", content)

        if content != original_content:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Fixed: {filepath}")

    except Exception as e:
        print(f"Error processing {filepath}: {e}")


def main():
    """Fix all test files."""
    tests_dir = Path("tests")
    if not tests_dir.exists():
        print("tests directory not found")
        return

    # Find all Python files in tests directory
    test_files = list(tests_dir.glob("**/*.py"))

    print(f"Found {len(test_files)} test files to process...")

    for test_file in test_files:
        fix_imports_in_file(test_file)

    print("Import fixing complete!")


if __name__ == "__main__":
    main()
