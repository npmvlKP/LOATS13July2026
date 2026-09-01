#!/usr/bin/env python3
"""
External verification script for TODO-23 (F7-L-03).

Verifies that FUNDAMENTAL, MACHINE_LEARNING, and OPTIONS_FLOW
are removed from StrengthEngine.source_weights to eliminate dead
configuration entries that have no production signal producers.

Exit codes:
    0 - Verification PASSED
    1 - Verification FAILED
"""

import re
import sys
from pathlib import Path


def _safe_symbols() -> tuple[str, str]:
    """Return PASS/FAIL symbols safe for both TTY and captured subprocess output.

    On Windows the default console encoding is cp1252, which cannot encode
    checkmark/cross symbols — printing them crashes with UnicodeEncodeError when
    stdout is a pipe (health-check child). Use ASCII when not a UTF-8 terminal.
    """
    try:
        if (
            sys.stdout.isatty()
            and sys.stdout.encoding
            and sys.stdout.encoding.lower().startswith("utf")
        ):
            return ("[PASS]", "[FAIL]")
    except Exception:
        pass
    return ("[PASS]", "[FAIL]")


_PASS_SYM, _FAIL_SYM = _safe_symbols()


def verify_dead_weights_removed() -> tuple[bool, str]:
    """
    Verify that dead weight entries are removed from strength.py.

    Returns:
        (is_valid, message) - True if valid, False with error message otherwise
    """
    strength_file = Path(__file__).parent.parent / "src" / "loats" / "strength.py"

    if not strength_file.exists():
        return False, f"strength.py not found at {strength_file}"

    content = strength_file.read_text()

    # Extract the source_weights dictionary initialization
    weights_pattern = r"source_weights\s*=\s*\{([^}]+)\}"
    match = re.search(weights_pattern, content, re.DOTALL)

    if not match:
        return False, "Could not find source_weights dictionary in strength.py"

    weights_content = match.group(1)

    # Check that dead weight entries are NOT present
    dead_weights = [
        "StrengthSource.FUNDAMENTAL",
        "StrengthSource.MACHINE_LEARNING",
        "StrengthSource.OPTIONS_FLOW",
    ]

    for dead_weight in dead_weights:
        if dead_weight in weights_content:
            return False, f"Dead weight {dead_weight} still present in source_weights"

    return True, "Dead weight entries removed from source_weights"


def verify_enum_still_defined() -> tuple[bool, str]:
    """
    Verify that the enum values are still defined in the StrengthSource enum.

    We only remove them from source_weights (the production configuration),
    but keep the enum definitions for future use when producers exist.

    Returns:
        (is_valid, message) - True if valid, False with error message otherwise
    """
    strength_file = Path(__file__).parent.parent / "src" / "loats" / "strength.py"

    content = strength_file.read_text()

    # These should still be in the enum
    enum_values = [
        'FUNDAMENTAL = "fundamental"',
        'MACHINE_LEARNING = "ml"',
        'OPTIONS_FLOW = "options_flow"',
    ]

    for enum_value in enum_values:
        if enum_value not in content:
            return False, f"Enum value {enum_value} removed from StrengthSource enum"

    return True, "Enum values still defined (ready for future producers)"


def main() -> int:
    """Run verification and report results."""
    print("=" * 60)
    print("TODO-23 (F7-L-03) External Verification")
    print("=" * 60)

    checks = [
        ("Dead weights removed from source_weights", verify_dead_weights_removed),
        ("Enum values still defined", verify_enum_still_defined),
    ]

    all_passed = True
    for check_name, check_fn in checks:
        print(f"\nChecking: {check_name}")
        is_valid, message = check_fn()

        if is_valid:
            print(f"{_PASS_SYM} {message}")
        else:
            print(f"{_FAIL_SYM} {message}")
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print(f"{_PASS_SYM} TODO-23 VERIFICATION PASSED")
        print("=" * 60)
        return 0
    else:
        print(f"{_FAIL_SYM} TODO-23 VERIFICATION FAILED")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
