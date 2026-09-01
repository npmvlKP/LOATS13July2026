#!/usr/bin/env python3
"""External verification: .env.example contains HC-23 trading config keys.

Run as a standalone script from the repository root:

    python scripts/verify_env_example_hc23.py

It checks that .env.example declares the three environment variables required by
HC-23 config conformance (MODS, MAX_OPEN_POSITIONS, MIN_OPEN_POSITIONS) and that
each has the expected default value.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPECTED = {
    "MODS": "25",
    "MAX_OPEN_POSITIONS": "5",
    "MIN_OPEN_POSITIONS": "3",
}


def extract_env_vars(dotenv_path: Path) -> dict[str, str]:
    """Parse KEY=VALUE pairs from a dotenv-style file."""
    values: dict[str, str] = {}
    if not dotenv_path.exists():
        return values
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().split("#", 1)[0].strip()
    return values


def main() -> int:
    """Verify HC-23 keys are present in .env.example."""
    env_vars = extract_env_vars(REPO_ROOT / ".env.example")
    missing = []
    wrong_value = []
    for key, expected in EXPECTED.items():
        if key not in env_vars:
            missing.append(key)
            continue
        actual = env_vars[key].strip()
        # Allow trailing comments after the value.
        actual_clean = actual.split("#", 1)[0].strip()
        if actual_clean != expected:
            wrong_value.append((key, expected, actual_clean))

    if missing or wrong_value:
        print("[FAIL] HC-23 .env.example verification")
        for key in missing:
            print(f"  missing: {key}")
        for key, expected, actual in wrong_value:
            print(f"  wrong value for {key}: expected {expected}, got {actual}")
        return 1

    print("[PASS] HC-23 .env.example verification")
    for key in EXPECTED:
        print(f"  {key}={env_vars[key]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
