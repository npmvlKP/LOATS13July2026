# Async Audit Dual-Write Coverage Pin — Failed-Patch Forensic Recovery (2026-09-13)

**Date:** 2026-09-13 (Asia/Calcutta). **Base:** `main` @ `5aecef8`
(merge of PR #28). **Tree before wave:** clean, 411/411 tracked files
(ceiling 411). This record documents the disposition of the session's
file-mutation-verifier flag: a failed patch against
`tests/test_database_async_additions.py` (malformed target path
`...py1180` — a path/line concatenation artifact), and the coverage gap
it pointed at.

## Failed-patch forensics

The verifier flagged the failed patch target
`tests/test_database_async_additions.py` suffixed `1180` (a path/line
concatenation artifact) as NOT modified. Evidence gathered before any edit:

* `git status` at 01:27 IST: clean at `main @ 5aecef8`; no stash
  (`git stash list` empty); reflog clean (no lost wave work).
* File intact and green: 37/37 passed before any change.
* Session search for the failed patch's intent returned nothing
  (unrecoverable). Per house rule (zero fabrication), the intent was
  reconstructed **from repository evidence only**.
* Coverage re-measurement at HEAD: 80.61% (58 passed) over
  `loats.database` + `loats.database_async_additions`; the missing-line
  report named exactly one behavioral gap at the failed patch's anchor
  region: `database_async_additions.py:456-457` (the JSONL-write-failure
  → RuntimeError → DB-abort branch of the dual-write guarantee documented
  at database.py:749-753) plus the pool-None delegation branch (417-425).

Root cause of the flag: the failed patch itself was never a valid edit —
its target string was a concatenation artifact, so nothing landed and
nothing was lost. The honest disposition is to pin the unpinned
invariant it pointed at.

## Changes

1. `tests/test_database_async_additions.py` — two behavioral pins
   appended to `TestTradeDecisionAsyncDispatch`:
   * `test_async_log_audit_jsonl_failure_aborts_db_write` — points the
     audit path at a REAL directory (real filesystem failure, no mock);
     asserts RuntimeError with the dual-write-abort message and that the
     DB trail has zero rows for the entity (the commit never happened).
   * `test_async_log_audit_no_pool_delegates_to_sync_dual_write` — calls
     the bound `_async_log_audit` directly with the pool absent; asserts
     the entry lands in BOTH trails with the SAME sha256 hash.
   Both use the codebase convention `cast("Any", temp_db)` for
   runtime-bound attributes (database.py:2537).
2. `docs/audit-history/13Sep2026-async-audit-dual-write-pin.md` — this
   record (ceiling-neutral: paired with removal of
   `docs/audit-history/minimal_test.py`, verified zero-reference across
   scripts/tests/src/docs/.github before deletion).

## Verification (measured, not drafted)

* GREEN on correct code: 39 collected / 2 selected passed
  (`-k "jsonl_failure or no_pool_delegates"`).
* **Mutation legs (RED proof):**
  * Mutant A2 (swallow JSONL failure → DB commit proceeds): pin 1
    FAILED under mutant — detects the invariant break. (An earlier
    A-mutant injected `logger.warning` into a module that never imports
    `logger`, producing NameError → wrapper fallback → sync path raised
    the same RuntimeError — test stayed green because the OUTER contract
    held via defense-in-depth, not because the pin was weak.)
  * Mutant B2 (sever the pool-None delegation): pin 2 FAILED with
    `assert 0 == 1` — no JSONL row lands.
  * Source restored after each mutant (`git checkout --`), tree clean.
* Coverage re-measured: **60 passed, 81.60% total** (was 80.61% at
  HEAD); `database_async_additions.py` 88%→**89%**, missing-lines 456-457
  and 417-425 eliminated from the report.
* Bandit (CI scope, `bandit -r src/ -c pyproject.toml`): rc=0, zero
  findings, 15,211 LOC.
* Ruff check + format --check + flake8 on the test file: all rc=0
  (one reformat of a line-1289 comprehension applied).
* Full suite: see wave section below (background run gated commit 1).

## Wave section

Verification at this tree (all commands run with the repo venv first on
PATH, exit codes captured unpiped):

* Full suite: **1807 passed, 0 failed**, rc=0 in 387.49s (background
  run; includes the two new pins and the pre-existing 11-test
  trade-decision net).
* mypy (CI-exact `mypy src/ --strict --config-file pyproject.toml`):
  "Success: no issues found in 38 source files", rc=0.
* Bandit (CI-exact `bandit -r src/ -c pyproject.toml -f json`): rc=0,
  zero findings, 15,211 LOC.
* Coverage (targeted, this wave's modules): 60 passed, **81.60%**
  (HEAD baseline was 80.61%); the two targeted missing-line ranges are
  eliminated from the report.
* Mutation RED legs: pin 1 fails under swallow-and-commit mutant A2;
  pin 2 fails with `assert 0 == 1` under severed-delegation mutant B2.
* Ceiling-neutral accounting: commit 1 (append-only test file) and
  commit 2 (+1 record / −1 `docs/audit-history/minimal_test.py`) hold
  the tracked tree at 411 = `ratchet_baseline.TRACKED_FILE_CEILING`;
  no ratchet edit required (house pattern: the 397 wave's +1/−0
  offset). Delivery through the protected-main PR pipeline per the
  git-protected-main procedure; PR number and CI run id live in the
  merge evidence, not in this record.


## Carried risks (unchanged from the 13Sep wave record)

* P1 close/downgrade decision fires Mon 14 Sep 09:15 IST (cron
  e7a576fe42f7) — time-gated, machinery armed.
* P5 decisional clock: earliest gate PASS ~26 Sep; Wed re-check cron
  5726663ee918; route-watch d6fd51ca3481 standing tripwire.
* P2: upstream PR #2047 open+mergeable, awaiting maintainer.
* R6 nltk waiver standing (ADR-0010); R8 F8-L backlog queued.
