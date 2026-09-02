#!/usr/bin/env python3
"""Repository hygiene guard (F8-C-02).

Rejects tracked files that must never enter the index: virtual
environments, machine-local junk directories, tool output that is
re-derivable, and secrets-adjacent env files. Exit 0 = clean, exit 1 =
violations found (printed, one per line).

Usage:
    python scripts/check_repo_hygiene.py [--json PATH]

Integrated as:
    - CI job `repo-hygiene` (.github/workflows/ci.yml)
    - pre-commit hook `repo-hygiene`
    - FR7 health check HC-26 extension (delegated, same as HC-13 pattern)
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Patterns matched against tracked paths (fnmatch, forward slashes).
# A match means "must NOT be tracked".
FORBIDDEN_PATTERNS: tuple[str, ...] = (
    # Virtual environments (F8-C-02 core finding)
    "loatsNEW/*",
    ".venv/*",
    "venv/*",
    "ENV/*",
    "*/pyvenv.cfg",
    "*/Scripts/python.exe",
    "*/Scripts/pythonw.exe",
    "*/bin/python",
    "*/bin/python3",
    "*/Lib/site-packages/*",
    "*/lib/python3*/site-packages/*",
    # Machine-local junk (PowerShell `~` expansion mishap)
    "~/*",
    # Tool output / re-derivable artifacts
    "node_modules/*",
    "htmlcov/*",
    "mypy-report/*",
    ".mypy_cache/*",
    ".pytest_cache/*",
    ".ruff_cache/*",
    "coverage.json",
    ".coverage",
    # Secrets-adjacent env files (.env.example stays tracked)
    ".env",
    ".env.test",
    ".env.prod",
    ".env.local",
    ".env.development",
)

# Hard ceiling on tracked files. 369 = measured count at commit 7a2ea233^
# (the legitimate tree immediately before the TODO-25 venv sweep). The
# TODO-21 ratchet (<=343) went stale after TODO-22..27 additions; this
# ceiling preserves the ratchet intent without freezing legitimate growth.
TRACKED_FILE_CEILING = 420

# Tracked paths that would match FORBIDDEN_PATTERNS but are deliberate.
ALLOWLIST: frozenset[str] = frozenset(
    {
        # Example template, intentionally tracked (referenced by
        # scripts/check_env_settings_sync.py / HC-23).
        ".env.example",
    }
)

# Paths that must not appear untracked-but-present at the repo root either
# (workspace cleanliness probe - informational when untracked, since
# .gitignore already covers them; enforced on the tracked set above).
ROOT_JUNK_NAMES: tuple[str, ...] = (
    "-p",
    "G......",
    "0.21.0",
    "$null",
    "[100%]",
    "tmp_schema.db",
    "pytest_output.txt",
)


def _tracked_files() -> list[str]:
    """Return the tracked path list via `git ls-files`."""
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        shell=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {proc.stderr.strip()}")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _violations(paths: list[str]) -> list[tuple[str, str]]:
    """Return (path, pattern) pairs for tracked paths matching a pattern."""
    hits: list[tuple[str, str]] = []
    for path in paths:
        if path in ALLOWLIST:
            continue
        for pattern in FORBIDDEN_PATTERNS:
            # Anchored match for root-level names, glob match otherwise.
            if "/" not in pattern.strip("*"):
                if path == pattern:
                    hits.append((path, pattern))
                    break
            elif fnmatch.fnmatch(path, pattern):
                hits.append((path, pattern))
                break
    return hits


def _root_junk() -> list[str]:
    """Return forbidden root junk names that exist on disk."""
    return [n for n in ROOT_JUNK_NAMES if (REPO_ROOT / n).exists()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", default="", help="write summary JSON to this path")
    args = ap.parse_args()

    try:
        tracked = _tracked_files()
    except RuntimeError as exc:
        print(f"[FAIL] {exc}")
        return 1

    violations = _violations(tracked)
    junk = _root_junk()
    ceiling_breach = len(tracked) > TRACKED_FILE_CEILING

    problems: list[str] = []
    for path, pattern in violations:
        problems.append(f"tracked path matches forbidden pattern '{pattern}': {path}")
    for name in junk:
        problems.append(f"root junk artifact present: {name}")
    if ceiling_breach:
        problems.append(
            f"tracked file count {len(tracked)} exceeds ceiling {TRACKED_FILE_CEILING}"
        )

    summary = {
        "tracked_files": len(tracked),
        "ceiling": TRACKED_FILE_CEILING,
        "pattern_violations": len(violations),
        "root_junk": junk,
        "problems": problems,
        "status": "PASS" if not problems else "FAIL",
    }

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if problems:
        print(f"[FAIL] repo hygiene: {len(problems)} problem(s)")
        for p in problems[:50]:
            print(f"  - {p}")
        if len(problems) > 50:
            print(f"  ... and {len(problems) - 50} more")
        print(
            "\nRemediation: git rm -r --cached <path> and add the path to "
            ".gitignore (see F8-C-02 report)."
        )
        return 1

    print(
        f"[PASS] repo hygiene: {len(tracked)} tracked files "
        f"(ceiling {TRACKED_FILE_CEILING}), no forbidden patterns, no root junk"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
