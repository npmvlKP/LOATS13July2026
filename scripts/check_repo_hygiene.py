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
import os
import re
import subprocess
import sys
from pathlib import Path

# win32_root_junk lives next to this script; import works both when run
# as a script (sys.path[0] = scripts/) and when loaded as a module via
# importlib (tests/verifiers) after sys.path is seeded here.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import win32_root_junk  # noqa: F401  (lockstep pin via guard.win32_root_junk)
from ratchet_baseline import TRACKED_FILE_CEILING

REPO_ROOT = Path(__file__).resolve().parent.parent

# F8-M-05 / ADR-0011: root-level reports/*.json are verifier run artifacts
# (machine-local state, absolute paths) — the curated evidence of record
# lives in dated snapshots under reports/<subdir>/. Single-segment match:
# fnmatch globs would cross "/" and false-positive the curated subdirs.
_TOP_LEVEL_REPORT_ARTIFACT = re.compile(r"reports/[^/]+\.json")

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

# Hard ceiling on tracked files: single source of truth in
# scripts/ratchet_baseline.py (F8-L-07). This constant was previously
# hand-pinned here AND in three verifier scripts; re-pinning one surface
# without the others left committed gates failing on a clean tree (the
# 416-vs-426 lockstep split). Re-pin protocol: edit
# ratchet_baseline.TRACKED_FILE_CEILING only, run the lockstep tests
# (tests/test_repo_hygiene.py::TestRatchetSingleSource,
# tests/test_todo25_verifier_gates.py::TestRatchetLockstep).
# scripts/ orphans are separately ratcheted by
# scripts/check_scripts_wiring.py (CI repo-hygiene, pre-commit, HC-30).

# Tracked paths that would match FORBIDDEN_PATTERNS / the root-level
# reports/*.json artifact rule but are deliberate evidence of record with
# tracked consumers. Adding an entry requires naming its consumer in the
# comment (the wiring guard fails when a citation goes dead — F8-L-06-R2).
ALLOWLIST: frozenset[str] = frozenset(
    {
        # Example template, intentionally tracked (referenced by
        # scripts/check_env_settings_sync.py / HC-23).
        ".env.example",
        # Canonical P1 discharge evidence of record (100/100 live TCS round
        # trips). Pinned in .gitignore by negation; consumed by
        # verify_todo25_* and required by HC-29 from a fresh clone.
        "reports/p1_analyze_latency_20260904_040609.json",
        # FR7 production-status verification record; cited by
        # docs/audit-history/FR7_PRODUCTION_STATUS.md.
        "reports/production-verification.json",
        # TODO-27 decision inputs, consumed by the tracked verifiers
        # scripts/verify_todo27_eval.py and scripts/verify_todo27_external.py.
        "reports/todo27_eval.json",
        "reports/todo27_external.json",
        # F8-H-01 external verification record; consumed by
        # scripts/verify_f8h01_external.py and cited by
        # docs/ADR-006-analyzer-routing-p5.md and the F8-L-06 closure note.
        "reports/verify_f8h01_external.json",
    }
)

# Paths that must not appear untracked-but-present at the repo root either
# (workspace cleanliness probe - informational when untracked, since
# .gitignore already covers them; enforced on the tracked set above).
# The name list itself lives in scripts/win32_root_junk.py (F8-M-03) and is
# imported above, so the hygiene guard, fr7_health_check HC-26, and the HC
# registry verifier share one Win32-safe detection implementation.


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
        # F8-M-05 / ADR-0011: run artifacts live at the TOP level of
        # reports/ only (single-segment rule). fnmatch globs cross "/", so
        # "reports/*.json" would also condemn the deliberate evidence of
        # record in curated subdirectories (reports/security/,
        # reports/health/, reports/ai-generated/, reports/performance/ and
        # reports/p1_analyze_latency_*.json); those are governed by
        # TestCompactRepoDocs instead. A single-segment regex pins the
        # top-level rule without that false-positive class.
        if _TOP_LEVEL_REPORT_ARTIFACT.fullmatch(path):
            hits.append((path, "reports/*.json (root-level run artifact)"))
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
    """Return forbidden root junk names that exist on disk (Win32-safe)."""
    # F8-M-03: delegate to the shared Win32-safe detector. Path.exists()
    # misses trailing-dot names on Windows (and aliases onto dot-stripped
    # phantom siblings); os.scandir membership is sound in both directions.
    # F8-M-04: root_junk_findings additionally flags the CLASS of
    # Win32-hostile verbatim names (trailing dots/spaces, colons,
    # reserved device names), so a future shell-redirection mishap with
    # a NEW junk name fails here instead of materializing invisibly.
    from win32_root_junk import root_junk_findings

    return root_junk_findings(REPO_ROOT)


# F8-H-01 evidence-stream guard (2026-09-08): test/verification invocations
# of scripts/run_p5_forward_test.py are required to redirect run-log writes
# via P5_RUN_LOG_DIR (the isolation mechanism tests/ already pin); a dry-run
# stub landing in the production evidence stream means a caller skipped it.
# Matches only the dry-run stub grammar — live supervised logs (dry_run
# false) are never flagged, so the gate can never block a real run.
def _p5_dry_run_stubs() -> list[str]:
    stubs: list[str] = []
    reports = REPO_ROOT / "reports"
    if not reports.is_dir():
        return stubs
    for entry in os.scandir(reports):
        if not (entry.is_file() and entry.name.startswith("p5_forward_test_")):
            continue
        if not entry.name.endswith(".json"):
            continue
        try:
            with open(entry.path, encoding="utf-8") as fh:
                head = fh.read(2048)
            if '"dry_run": true' not in head and "'dry_run': True" not in head:
                continue
            with open(entry.path, encoding="utf-8") as fh:
                meta = json.load(fh).get("metadata", {})
        except (OSError, ValueError):
            continue
        if (
            meta.get("phase_gate") == "P5"
            and meta.get("script") == "scripts/run_p5_forward_test.py"
            and meta.get("dry_run") is True
        ):
            stubs.append(entry.name)
    return stubs


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
    p5_stubs = _p5_dry_run_stubs()
    ceiling_breach = len(tracked) > TRACKED_FILE_CEILING

    problems: list[str] = []
    for path, pattern in violations:
        problems.append(f"tracked path matches forbidden pattern '{pattern}': {path}")
    for name in junk:
        problems.append(f"root junk artifact present: {name}")
    for name in p5_stubs:
        problems.append(
            f"dry-run stub in the production P5 evidence stream: reports/{name} "
            "(delete it; the caller must set P5_RUN_LOG_DIR - see F8-H-01)"
        )
    if ceiling_breach:
        problems.append(
            f"tracked file count {len(tracked)} exceeds ceiling {TRACKED_FILE_CEILING}"
        )

    summary = {
        "tracked_files": len(tracked),
        "ceiling": TRACKED_FILE_CEILING,
        "pattern_violations": len(violations),
        "root_junk": junk,
        "p5_dry_run_stubs": p5_stubs,
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
