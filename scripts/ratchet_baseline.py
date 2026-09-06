#!/usr/bin/env python3
"""Canonical tracked-file ratchet baseline (F8-L-07).

Single source of truth for the tracked-file ceiling. The 416-vs-426
split class: the same integer was hand-pinned in four gate scripts
(scripts/check_repo_hygiene.py, scripts/verify_f8c02_external.py,
scripts/verify_todo21_external.py, scripts/verify_todo21_root_cleanup.py);
re-pinning one surface without the others left committed gates failing
on a clean tree. Every ratchet surface now imports TRACKED_FILE_CEILING
from this module, so lockstep is structural rather than procedural.

Re-pin protocol (next wave that changes the tracked-file count):
  1. Edit TRACKED_FILE_CEILING here — the ONLY place the number lives.
  2. Update the history block below (wave ID, +/- file delta, new value).
  3. Run: pytest tests/test_repo_hygiene.py tests/test_todo25_verifier_gates.py
     TestRatchetSingleSource/TestRatchetLockstep assert every surface
     resolves to this value at runtime; a missed surface fails them.

No other constant belongs here: keep this module import-free (stdlib
only, no side effects) so every consumer can load it in any context
(CI, pre-commit, health-check subprocess, importlib spec-load).

History (most recent last):
  369  measured count at 7a2ea233^ (immediately before the TODO-25 venv
       sweep; the TODO-21 ratchet <=343 had gone stale).
  415  F8-M-02 hygiene follow-up (2026-09-03): 16 session-agent files
       untracked; tree re-measured at 411.
  416  +1 docs/audit-history/03Sep2026-F8-L-03-closure.md.
  425  F8-L-05 (2026-09-04): +9 RSS-wave files.
  426  F8-L-06 (2026-09-04): +1 F8-L-06 closure record.
  429  TODO-25 gate-integrity wave (2026-09-04): +3, then +1 F8-L-03
       discharge evidence.
  377  F8-L-06-R2 (2026-09-05): -55 (48 dead one-wave scripts + 7
       orphaned report artifacts, ADR-0008), +3 wiring-guard files.
  379  F8-L-07 (2026-09-05): +2 (this module — the ceiling's new
       home — and its decision record docs/adr/
       0009-ratchet-baseline-single-source.md; see ADR-0009).
       scripts/ orphans are separately ratcheted by
       scripts/check_scripts_wiring.py (CI repo-hygiene, pre-commit,
       HC-30).
  380  CI/security workflow flag-drift repair wave (2026-09-06):
       +1 docs/adr/0010-nltk-dev-toolchain-triage.md (PYSEC-2026-3740
       triage decision record; see ADR-0010).
  382  Commit-gate observability wave (2026-09-06): +2
       (tests/test_commit_message_check.py — regression net for the
       cp1252 rejection crash and the F8-L-06-R2 format rule — and
       docs/adr/0011-security-report-artifacts.md; see ADR-0011). The
       same wave untracked 2 accidental git-add -A sweep-ins
       (reports/security/bandit.json, reports/security/
       safety-report.json — undated scan output; they were staged but
       never committed, so no committed file was removed).
"""

from __future__ import annotations

TRACKED_FILE_CEILING = 382
