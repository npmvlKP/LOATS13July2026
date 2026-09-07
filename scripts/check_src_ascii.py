#!/usr/bin/env python3
"""ASCII-conformance gate for source files under src/.

Exit codes:
    0: every scanned .py file conforms (pure ASCII outside the per-file
       test-pinned allowlist below)
    1: at least one file violates the contract, or a file could not be
       read (fail-closed)

Usage:
    python scripts/check_src_ascii.py

Why the gate looks like this (history, so the contract is not re-litigated):

* The original ``__main__`` called ``check_ascii_files()`` and discarded
  the returned bool, so the process exited 0 even when violations were
  found. The result is now the process exit code.
* The original contract demanded byte-pure ASCII across all of src/
  while ``src/loats/alerts.py`` deliberately embeds emoji in Telegram
  notification payloads pinned by ``tests/test_alerts.py`` (plus
  ``test_html_escaping_final.py`` / ``test_per_source_breakers.py``).
  A gate whose green state is unreachable can never be wired into CI or
  pre-commit -- it is a decorative gate, and it sat unwired since birth.
* This revision makes the green state reachable and the gate enforceable:
  typographic characters in comments/docstrings/log strings (em-dashes,
  arrows, comparison signs) are normalized to ASCII across src/, the
  test-pinned emoji payloads are enumerated per file in
  ``ALLOWED_NON_ASCII``, and every other non-ASCII character still fails
  closed. The gate runs in the CI ``repo-hygiene`` job and as a
  pre-commit hook, so the next non-ASCII source addition fails loudly
  instead of rotting silently.

ALLOWED_NON_ASCII policy: an entry is justified ONLY by behavior pinned
by a named test asserting the exact glyph in a rendered payload. Comments
and docstrings never qualify -- keep source prose ASCII.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Scan the real src/ tree of this repository (anchor to the script
# location instead of the process CWD, so the gate is stable no matter
# where it is invoked from).
SRC_DIR = Path(__file__).resolve().parent.parent / "src"

# Test-pinned notification payload glyphs, by file name under src/loats/.
# Every entry exists because a test asserts the exact glyph in a rendered
# alert message (tests/test_alerts.py and friends). Do not extend this
# table without a pinning test; do not add entries for prose characters.
ALLOWED_NON_ASCII: dict[str, frozenset[str]] = {
    "alerts.py": frozenset(
        {
            "\u26a0",  # warning sign (half of the warning-sign emoji)
            "\ufe0f",  # variation selector-16 (the other half)
            "\u2705",  # check mark button
            "\u274c",  # cross mark
            "\u26aa",  # white circle
            "\U0001f3af",  # direct hit
            "\U0001f4b0",  # money bag
            "\U0001f4b5",  # dollar banknote
            "\U0001f4b8",  # money with wings
            "\U0001f4ca",  # bar chart
            "\U0001f4cb",  # clipboard
            "\U0001f4c8",  # chart increasing
            "\U0001f4dd",  # memo
            "\U0001f504",  # counterclockwise arrows button
            "\U0001f534",  # red circle
            "\U0001f6a8",  # police car light
            "\U0001f6ab",  # prohibited
            "\U0001f7e2",  # green circle
        }
    ),
}


def check_ascii_files() -> bool:
    """Check source Python files for the ASCII conformance contract.

    A file conforms when every non-ASCII character it contains appears
    in that file's ``ALLOWED_NON_ASCII`` entry. Read failures are
    fail-closed: an unreadable file counts as a violation.
    """
    violations: list[str] = []
    total_files = 0

    for root, _, files in os.walk(SRC_DIR):
        for file in files:
            if not file.endswith(".py"):
                continue
            filepath = Path(root) / file
            total_files += 1
            try:
                content = filepath.read_text(encoding="utf-8")
            except Exception as e:  # gate must not crash; fail closed
                print(f"Error reading {filepath}: {e}")
                violations.append(str(filepath))
                continue

            allowed = ALLOWED_NON_ASCII.get(file, frozenset())
            bad_chars = {ch for ch in content if ord(ch) > 0x7F and ch not in allowed}
            if not bad_chars:
                continue
            bad_lines = sorted(
                {
                    lineno
                    for lineno, line in enumerate(content.splitlines(), 1)
                    for ch in line
                    if ord(ch) > 0x7F and ch not in allowed
                }
            )
            chars_desc = ", ".join(
                f"U+{ord(c):04X}" for c in sorted(bad_chars, key=ord)
            )
            lines_desc = ", ".join(str(n) for n in bad_lines[:10])
            if len(bad_lines) > 10:
                lines_desc += ", ..."
            violations.append(f"{filepath} (chars: {chars_desc}; lines: {lines_desc})")

    if violations:
        print(f"Found {len(violations)} files with non-ASCII characters:")
        for entry in violations:
            print(f"  {entry}")
    else:
        print(f"All {total_files} source files satisfy the ASCII contract.")

    return len(violations) == 0


if __name__ == "__main__":
    sys.exit(0 if check_ascii_files() else 1)
