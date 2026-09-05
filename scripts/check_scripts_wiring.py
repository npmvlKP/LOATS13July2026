#!/usr/bin/env python3
"""scripts/ orphans guard (F8-L-06-R2, maintainability ratchet).

Enforces the anti-rot invariants that keep scripts/ a *live* operations
surface instead of an archaeology site:

1. No wheel reinvention: ``src/`` and ``tests/`` must not import or
   subprocess anything from ``scripts/``. Test/gate entry points live in
   the test suite itself; a helper needed by both belongs in ``src/``.

2. Every ``scripts/*.py`` must be reachable from at least one live
   citation root: a CI workflow, the pre-commit config, tests/, src/,
   pyproject.toml, .flake8, README/RUNBOOK/CONTRIBUTING/DEPLOY,
   ``docs/`` (living docs only), the two pinned P1 evidence-of-record
   artifacts, or ANOTHER LIVE SCRIPT. Liveness is computed to a fixpoint
   starting from the non-scripts roots, so a clique of dead scripts
   citing only each other stays dead. A script reachable only from
   ``docs/audit-history/`` or ``reports/ai-generated/`` (frozen archives,
   which cite everything their wave ever touched) is an orphan.

Usage:
    python scripts/check_scripts_wiring.py            # exit 0/1
    python scripts/check_scripts_wiring.py --json P   # machine report

Integrated as:
    - CI job ``repo-hygiene`` (.github/workflows/ci.yml, same step)
    - pre-commit hook ``scripts-wiring``
    - delegated by fr7_health_check.py HC-30
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Non-scripts surfaces allowed to seed liveness. Frozen history archives
# are excluded on purpose: they cite everything their wave ever touched,
# so "cited only by the archive" means "dead".
_LIVE_SEARCH_PATHS = (
    ".github",
    ".pre-commit-config.yaml",
    "pyproject.toml",
    ".flake8",
    "src",
    "tests",
    "README.md",
    "RUNBOOK.md",
    "CONTRIBUTING.md",
    "DEPLOY.md",
    "docs",
    # Evidence-of-record artifacts pinned in .gitignore and verified by
    # verify_f8c02_external.py; their provenance field names the generator.
    "reports/p1_analyze_latency_20260828_084822.json",
    "reports/p1_analyze_latency_20260904_040609.json",
)
_ARCHIVE_HINTS = ("docs/audit-history/", "reports/ai-generated/")

# src//tests reaching into scripts/ is the wheel-reinvention vector: the
# win32_root_junk cross-import is the single grandfathered exception
# (guard-internal lockstep, test-pinned in tests/test_repo_hygiene.py).
_ALLOWED_SCRIPT_IMPORTS = frozenset({"win32_root_junk"})

_BACK_REF_PATTERN = r"^\s*(import|from)\s+(scripts[.\w]*|win32_root_junk)\b"


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        check=False,
    )
    if proc.returncode not in (0, 1):  # 1 = no matches, which is fine
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _tracked_script_names() -> list[str]:
    return [
        line.strip().removeprefix("scripts/")
        for line in _git("ls-files", "scripts/*.py").splitlines()
        if line.strip()
    ]


def _external_seeds(names: list[str]) -> dict[str, list[str]]:
    """Map script name -> non-scripts live surfaces citing it."""
    seeds: dict[str, list[str]] = {}
    for name in names:
        cited = [
            line.strip()
            for line in _git(
                "grep", "-l", "-F", name, "--", *_LIVE_SEARCH_PATHS
            ).splitlines()
            if line.strip() and not line.startswith(_ARCHIVE_HINTS)
        ]
        if cited:
            seeds[name] = cited
    return seeds


def _script_citations(name: str, live_names: set[str]) -> list[str]:
    """Live scripts/ files citing ``name`` (self-citations never count)."""
    return [
        line.strip().removeprefix("scripts/")
        for line in _git("grep", "-l", "-F", name, "--", "scripts").splitlines()
        if line.strip()
        and line.strip() != f"scripts/{name}"
        and line.strip().removeprefix("scripts/") in live_names
    ]


def _live_set(
    names: list[str],
    seeds: dict[str, list[str]],
    citations_fn=_script_citations,
) -> set[str]:
    """Fixpoint of liveness: seeds plus anything cited by a live script.

    Iterating from seeds (never the reverse) keeps dead cliques dead: two
    orphan scripts citing only each other have no seed and never become
    live, no matter how many rounds run. ``citations_fn`` is injectable
    for tests (name, live set) -> live scripts citing ``name``.
    """
    live = set(seeds)
    changed = True
    while changed:
        changed = False
        for name in names:
            if name in live:
                continue
            if citations_fn(name, live):
                live.add(name)
                changed = True
    return live


def _is_allowed_back_ref(line: str) -> bool:
    """True when a back-reference line names an allowed scripts/ module.

    Matches both the packaged form (``scripts.win32_root_junk`` /
    ``scripts/win32_root_junk``) and the sys.path-seeded direct import
    (``import win32_root_junk``) actually used by the guard and test
    surfaces (word-bounded, so ``cmp`` cannot swallow ``os.path.cmpx``).
    """
    return any(
        re.search(rf"\b(?:scripts[./])?{re.escape(n)}\b", line)
        for n in _ALLOWED_SCRIPT_IMPORTS
    )


def _back_reference_violations() -> list[str]:
    """src//tests reaching into scripts/ (wheel reinvention vector)."""
    raw = _git("grep", "-n", "-E", _BACK_REF_PATTERN, "--", "src", "tests")
    violations: list[str] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        if any(f"scripts/{n}" in line for n in _ALLOWED_SCRIPT_IMPORTS):
            continue
        violations.append(line)
    return violations


def check() -> tuple[list[str], dict[str, list[str]]]:
    """Return (violations, citations_by_script); empty list = clean."""
    names = _tracked_script_names()
    seeds = _external_seeds(names)
    live = _live_set(names, seeds)
    violations: list[str] = []
    citations: dict[str, list[str]] = {}
    for name in names:
        why = seeds.get(name) or _script_citations(name, live)
        citations[name] = why
        if name not in live:
            violations.append(
                f"orphan: scripts/{name} is cited by no live surface "
                f"(only frozen archives) — promote, archive, or delete"
            )
    for line in _back_reference_violations():
        violations.append(f"back-reference: {line}")
    return violations, citations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reject orphan scripts/ files and src//tests back-references."
    )
    parser.add_argument("--json", dest="json_path", type=Path, default=None)
    args = parser.parse_args(argv)

    violations, citations = check()

    if args.json_path is not None:
        payload = {
            "violations": violations,
            "scripts": len(citations),
            "citations": citations,
        }
        args.json_path.write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )

    if violations:
        print(f"SCRIPTS WIRING GUARD: {len(violations)} violation(s)")
        for v in violations:
            print(f"  {v}")
        print(
            "\nA scripts/ file must be reachable from a live citation root\n"
            "(CI, pre-commit, tests, src, pyproject, README/RUNBOOK/CONTRIBUTING/\n"
            "DEPLOY, living docs, pinned evidence artifacts) or from another\n"
            "live script. Citations only inside docs/audit-history/ or\n"
            "reports/ai-generated/ mean the script is a dead one-wave relic."
        )
        return 1

    print(f"OK scripts wiring clean ({len(citations)} scripts, all cited live)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
