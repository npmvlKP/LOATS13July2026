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
  383  CI parity wave (2026-09-06): +1
       (docs/adr/0012-ci-parity-linux-runners.md — decision record for
       the 26 GitHub-runner-only failures found by the first
       workflow_dispatch proof: editable-install contract, mypy
       platform-stub lambda, EXE001 exec bits, POSIX casefold gap,
       host-specific verifiers; see ADR-0012).
  382  DevOps workflow-integrity wave (2026-09-07): -1
       (reports/f8-h-03-verification.json — a zero-reference,
       machine-local verifier run artifact with embedded working-tree
       state and absolute paths — relocated to
       docs/audit-history/f8-h-03-verification-20260902.json per the
       ADR-0011 artifact discipline. The rename keeps the count at 382,
       so the ceiling now equals the tree: any net addition requires a
       deliberate re-pin.
  384  F8-M-02..07 closure wave (2026-09-07): +2
       (scripts/verify_f8m02_m07_external.py — the clean-process
       outcome verifier for risk-matrix rows F8-M-02..F8-M-07 — and
       docs/audit-history/07Sep2026-F8-M-02-M-07-closure.md, its
       closure record; see the record's External verifier section).
       Wired live by tests/test_repo_hygiene.py::
       TestF8M02M07ExternalVerifier.
  386  Shebang exec-bit normalizer wave (2026-09-07): +2
       (scripts/ensure_shebang_exec_bit.py — the ADR-0013 self-healing
       pre-commit normalizer for the Windows 100644 shebang class —
       and its decision record
       docs/adr/0013-shebang-exec-bit-normalizer.md).
  387  F8-H-01 forward-test integrity (2026-09-07): +1
       (tests/test_f8h01_fixes.py — regression net for the producer
       window, the validator's decisional-activity criterion, the
       P5_RUN_LOG_DIR runner isolation, and the conftest test-data
       isolation; ADR-006 Amendment 2).
  389  F8-H-01 P2 follow-up (2026-09-07): +2
       (scripts/quarantine_test_data.py — fingerprint-only quarantine
       of test-contaminated trade decisions into
       trade_decisions_quarantined, audit trail untouched; and its
       regression net tests/test_quarantine_test_data.py).
  390  ASCII gate contract wave (2026-09-07): +1
       (docs/adr/0014-src-ascii-gate-contract.md — the born-red,
       never-wired src ascii gate made enforceable: prose characters
       normalized to ASCII across src/, test-pinned alert emoji
       enumerated in the gate's ALLOWED_NON_ASCII, gate wired into the
       CI repo-hygiene job and pre-commit; see ADR-0014).
  391  F8-H-04 closure wave (2026-09-07): +1
       (docs/audit-history/07Sep2026-F8-H-04-closure.md — outcome
       evidence for the restored FR floor map at HEAD af37d33: fresh
       1553-test run, aggregate 87.33%, all ten floor-mapped modules
       green; closure record for register item 5).
  393  Carried-set reconciliation wave (2026-09-07): +2
       (docs/audit-history/07Sep2026-carried-set-reconciliation.md —
       register item 8 re-derived against the tree: seven of eight
       carried items CLOSED/DISCHARGED with pinned evidence,
       as_of_date registered as the sole open item; and
       scripts/verify_carried_set_external.py — the clean-process
       outcome verifier for those dispositions, wired live by
       tests/test_repo_hygiene.py::TestCarriedSetExternalVerifier).
  394  F8-L-02 acceptance net wave (2026-09-07): +1
       (tests/test_as_of_date_propagation.py — 11-test acceptance net
       for the caller-supplied as_of_date propagation into
       decision/audit records: model field, engine + orchestrator
       parameters, trade_decisions column round trip, CREATE/ROUTE
       audit rows, and the zero-date.today() invariant).
  395  F8-L-02 closure-record wave (2026-09-07): +1
       (docs/audit-history/07Sep2026-F8-L-02-closure.md — the closure
       record for the register's last open item, with the wave's
       implementation surfaces, behaviour contract, and acceptance
       evidence. Carried set now eight of eight CLOSED/DISCHARGED).
"""

from __future__ import annotations

TRACKED_FILE_CEILING = 394
