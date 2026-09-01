#!/usr/bin/env python3
"""Check for PYTEST_CURRENT_TEST bypass patterns in src/."""

import pathlib
import sys


def main() -> int:
    src = pathlib.Path("src")
    matches = []
    for p in src.rglob("*.py"):
        t = p.read_text(encoding="utf-8")
        if "PYTEST_CURRENT_TEST" in t:
            matches.append(str(p))

    if matches:
        print(f"FAIL: PYTEST_CURRENT_TEST bypass found in: {matches}")
        return 1
    else:
        print("PASS: no PYTEST_CURRENT_TEST bypass")
        return 0


if __name__ == "__main__":
    sys.exit(main())
