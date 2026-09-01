#!/usr/bin/env python3
"""Inspect async methods on Database class."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from loats.database import Database


def main() -> int:
    async_methods = [m for m in dir(Database) if "async" in m or m.startswith("_async")]
    print(sorted(async_methods))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
