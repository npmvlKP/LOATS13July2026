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

    # Check for presence of dead weights in source_weights
    dead_sources = [
        "StrengthSource.FUNDAMENTAL",
        "StrengthSource.MACHINE_LEARNING",
        "StrengthSource.OPTIONS_FLOW",
    ]

    # Find the source_weights dictionary definition
    # Look for the pattern within __init__ method
    init_pattern = r'def __init__\(self\).*?self\.source_weights\s*=\s*\{.*?\n\s*\}'
    match = re.search(init_pattern, content, re.DOTALL)

    if not match:
        return False, "Could not find source_weights dictionary in StrengthEngine.__init__"

    source_weights_block = match.group(0)

    # Check that none of the dead sources are in the source_weights block
    violations = []
    for source in dead_sources:
        if source in source_weights_block:
            violations.append(source)

    if violations:
        return False, (
            f"Dead weight entries found in source_weights: {violations}. "
            "These sources have no production signal producers."
        )

    # Verify that the TODO-23 comment is present
    if "TODO-23" not in source_weights_block and "FUNDAMENTAL, MACHINE_LEARNING, OPTIONS_FLOW removed" not in content:
        return False, (
            "TODO-23 removal comment not found. "
            "Expected comment explaining removal of dead weights."
        )

    # Verify that active sources are still present
    active_sources = [
        "StrengthSource.TECHNICAL_ANALYSIS",
        "StrengthSource.SENTIMENT",
        "StrengthSource.PRICE_ACTION",
        "StrengthSource.VOLATILITY",
    ]

    for source in active_sources:
        if source not in source_weights_block:
            return False, f"Active source {source} missing from source_weights"

    return True, "Verification passed: dead weights removed, active sources present, TODO-23 documented"


def verify_enum_still_defined() -> tuple[bool, str]:
    """
    Verify that the enum values are still defined (even if not used in weights).

    This is intentional - the enum values exist for future producer implementation,
    they're just not weighted until producers exist.

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
            print(f"✓ {message}")
        else:
            print(f"✗ {message}")
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("✓ TODO-23 VERIFICATION PASSED")
        print("=" * 60)
        return 0
    else:
        print("✗ TODO-23 VERIFICATION FAILED")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())