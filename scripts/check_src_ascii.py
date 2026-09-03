#!/usr/bin/env python3
"""ASCII-conformance gate for source files under src/.

Exit codes (F8-M-06):
    0: every scanned .py file is pure ASCII
    1: at least one file contains non-ASCII characters, or a file could
       not be read (fail-closed)

Usage:
    python scripts/check_src_ascii.py

The historical defect: ``__main__`` called ``check_ascii_files()`` and
discarded the returned bool, so the process exited 0 (success) even when
violations were found. The result is now the process exit code.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Scan the real src/ tree of this repository (anchor to the script
# location instead of the process CWD, so the gate is stable no matter
# where it is invoked from).
SRC_DIR = Path(__file__).resolve().parent.parent / "src"


def check_ascii_files() -> bool:
    """Check source Python files for non-ASCII characters.

    Returns True when every scanned file is pure ASCII. Read failures
    are fail-closed: an unreadable file counts as a violation.
    """
    non_ascii_files: list[str] = []
    total_files = 0

    for root, _, files in os.walk(SRC_DIR):
        for file in files:
            if file.endswith(".py"):
                filepath = Path(root) / file
                total_files += 1
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    if not re.match(r"^[\x00-\x7F]*$", content):
                        non_ascii_files.append(str(filepath))
                except Exception as e:  # gate must not crash; fail closed
                    print(f"Error reading {filepath}: {e}")
                    non_ascii_files.append(str(filepath))

    if non_ascii_files:
        print(f"Found {len(non_ascii_files)} files with non-ASCII characters:")
        for file in non_ascii_files:
            print(f"  {file}")
    else:
        print(f"All {total_files} source files contain only ASCII characters.")

    return len(non_ascii_files) == 0


if __name__ == "__main__":
    sys.exit(0 if check_ascii_files() else 1)
