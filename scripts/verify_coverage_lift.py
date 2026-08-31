#!/usr/bin/env python3
"""Verify coverage lift for performance_analyzer, rules, and sizing modules."""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "buffer") and not isinstance(
            sys.stdout, io.TextIOWrapper
        ):
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer,
                encoding="utf-8",
                errors="replace",
                line_buffering=True,
            )
        if hasattr(sys.stderr, "buffer") and not isinstance(
            sys.stderr, io.TextIOWrapper
        ):
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer,
                encoding="utf-8",
                errors="replace",
                line_buffering=True,
            )
    except (OSError, ValueError, AttributeError):
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        os.environ.setdefault("PYTHONUTF8", "1")

REPO_ROOT = Path(__file__).resolve().parent.parent
PASS_SYM = "[PASS]"
FAIL_SYM = "[FAIL]"


def get_module_coverage(module_name: str) -> float:
    """Get coverage percentage for a specific module from coverage.json."""
    cov_file = REPO_ROOT / "coverage.json"
    if not cov_file.exists():
        return 0.0
    try:
        with open(cov_file, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return 0.0
    for file_path, file_data in data["files"].items():
        if module_name in file_path.replace("\\", "/"):
            return file_data["summary"]["percent_covered"]
    return 0.0


def main() -> int:
    print("=" * 70)
    print("COVERAGE LIFT VERIFICATION")
    print("=" * 70)

    modules = {
        "performance_analyzer": {"before": 0.0, "target": 80.0},
        "rules": {"before": 23.4, "target": 80.0},
        "sizing": {"before": 32.7, "target": 80.0},
    }

    print("\nModule Coverage Comparison:")
    print("-" * 70)

    all_ok = True
    for module, info in modules.items():
        current = get_module_coverage(module)
        before = info["before"]
        target = info["target"]
        delta = current - before
        ok = current >= target

        print(
            f"{PASS_SYM if ok else FAIL_SYM}: {module:25s} {before:6.1f}% -> {current:6.1f}% "
            f"(delta: {delta:+6.1f}%, target: {target:.0f}%)"
        )
        all_ok = all_ok and ok

    cov_file = REPO_ROOT / "coverage.json"
    if cov_file.exists():
        try:
            with open(cov_file, encoding="utf-8") as f:
                data = json.load(f)
            agg = data["totals"]["percent_covered"]
        except (json.JSONDecodeError, OSError):
            agg = 0.0
        print(f"\nAggregate: {agg:.1f}% (target: 80.0%)")
        print(f"Aggregate {PASS_SYM if agg >= 80.0 else FAIL_SYM}")
        all_ok = all_ok and (agg >= 80.0)

    print("=" * 70)
    if all_ok:
        print("COVERAGE LIFT VERIFICATION PASSED")
        return 0
    print("COVERAGE LIFT VERIFICATION FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
