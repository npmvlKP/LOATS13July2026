#!/usr/bin/env python3
"""
Commit message validation script to prevent misleading deployment-ready claims.

This script enforces the policy defined in CONTRIBUTING.md that prohibits
commit messages from claiming deployment readiness.
"""

import codecs
import os
import sys


def main():
    # Get the commit message file path from command line arguments
    if len(sys.argv) < 2:
        print("ERROR: No commit message file provided")
        sys.exit(1)

    commit_msg_file = sys.argv[1]

    # Read the commit message
    try:
        with open(commit_msg_file, "r", encoding="utf-8") as f:
            commit_message = f.read()
    except FileNotFoundError:
        print(f"ERROR: Commit message file not found: {commit_msg_file}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR reading commit message file: {e}")
        sys.exit(1)

    # Define prohibited phrases (case-insensitive)
    prohibited_phrases = [
        "ready for deployment",
        "production ready",
        "ready for production",
        "deployment ready",
        "production-ready",
        "deployment-ready",
    ]

    # Check for prohibited phrases
    found_violations = []
    for phrase in prohibited_phrases:
        if phrase.lower() in commit_message.lower():
            found_violations.append(phrase)

    # If violations found, reject the commit
    if found_violations:
        print("ERROR COMMIT REJECTED: Commit message contains prohibited phrases:")
        for phrase in found_violations:
            print(f"  - '{phrase}'")

        print("\n" + "=" * 60)
        print("COMMIT MESSAGE POLICY VIOLATION")
        print("=" * 60)
        print("According to CONTRIBUTING.md guidelines, commit messages")
        print("must not claim deployment readiness. Only the QA gate may")
        print("declare production readiness after comprehensive testing.")
        print()
        print("Please revise your commit message to use descriptive")
        print("language about what was accomplished instead of claiming")
        print("deployment readiness.")
        print()
        print("See CONTRIBUTING.md for examples of acceptable formats.")
        print("=" * 60)

        sys.exit(1)

    # If no violations, allow the commit
    # Use ASCII-compatible checkmark for Windows compatibility
    print("OK Commit message validation passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
