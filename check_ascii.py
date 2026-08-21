import os
import re
from pathlib import Path


def check_ascii_files() -> bool:
    """Check all Python files for non-ASCII characters."""
    non_ascii_files: list[str] = []
    total_files = 0

    for root, _, files in os.walk("."):
        for file in files:
            if file.endswith(".py"):
                filepath = Path(root) / file
                total_files += 1
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                        if not re.match(r"^[\x00-\x7F]*$", content):
                            non_ascii_files.append(str(filepath))
                except Exception as e:
                    print(f"Error reading {filepath}: {e}")

    if non_ascii_files:
        print(f"Found {len(non_ascii_files)} files with non-ASCII characters:")
        for file in non_ascii_files:
            print(f"  {file}")
    else:
        print(f"All {total_files} Python files contain only ASCII characters.")

    return len(non_ascii_files) == 0


if __name__ == "__main__":
    check_ascii_files()
