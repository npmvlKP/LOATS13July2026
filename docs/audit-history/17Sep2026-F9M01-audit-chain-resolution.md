# F9-M-01 (TODO-6) — SHA-256 Chained Audit Trail: Root Cause & Resolution

**Finding:** FR9 §3 F9-M-01 — "Audit trail is self-hashed, NOT chained:
'SHA-256 chain' (CMP §2/§4/§6 kept-list) unimplemented." Severity Medium,
confidence Certain, remediation TODO-6.

**Status:** RESOLVED 2026-09-17 (this wave). Live supervisor unaffected:
the schema migration is idempotent and only executes at a `Database`
construction — for the live `data/loats.db` that is the post-30Sep
restart; until then legacy rows keep `previous_hash` NULL and remain
fully verifiable under the grandfathered rule.

## Root cause (verified)

`verify_audit_log_integrity()` re-computed each entry's hash over its own
fields only. Any deletion or REORDERING of entries leaves every self-hash
intact — the corruption classes that matter for tamper evidence were
undetectable, while README:163 claimed "SHA-256 chained". Live-probed
before the wave: reordering two entries and deleting a middle entry both
verified TRUE under the old verifier (pinned RED: `3 passed / 12 failed`
pre-fix, the 3 passes being exactly the tamper cases self-hashing cannot
see).

## Remediation (TODO-6 spec, complete)

1. **`previous_hash` column** on `audit_log` — appended LAST in both the
   fresh CREATE TABLE and the ALTER migration (positional-index contract
   with the row reader, F8-L-02 convention, index 11; fresh and migrated
   schemas pinned byte-equal by test).
2. **Genuine chain**: hash = sha256(canonical entry INCLUDING
   `previous_hash`); the link is load-bearing (pin proves stripping it
   changes the self-hash). Both JSONL line and DB row carry it; the
   writer seeds from the last line's `sha256_hash` read back in file
   order (`_read_chain_head`), so the chain survives process restarts.
3. **Link-walking verifier**: two layers, file order — self-hash per
   entry (unchanged semantics) + chain link for every entry carrying the
   key. Grandfathering waives the LINK check for pre-chain entries only,
   never the self-hash check. Any failure logs a **CRITICAL** alert
   naming the entry and the tamper class, then returns False.
4. **Head-seed migration**: no data rewrite — the first post-migration
   entry links at the legacy head; the legacy prefix is preserved
   verbatim (pinned).
5. **Second writer covered**: `_async_log_audit` (aiosqlite pool path)
   carries the identical chain semantics and INSERT column.

## TDD evidence

- RED-first: `tests/test_audit_chain_f9m01.py` — 12 failed / 3 passed
  (the 3 passes = delete/reorder/reorder-class cases invisible to the old
  verifier, re-pinned as the motivation).
- GREEN: 15/15 new pins; 110 passed across
  `test_database` + `test_database_async_additions` +
  `test_e2e_cmp_chain` + `test_per_source_breakers`; full repo suite green
  on the staged tree (ratchet lockstep included).
- Gates: ruff repo-scope clean, ruff format clean, isort clean, flake8
  clean, pre-commit mypy strict **Passed**, bandit clean.

## P5 span-safety statement

The audit WRITE path changes (new column + link computation), but the
live supervisor runs pre-wave code until its restart. The migration runs
only inside `Database.__init__` — never triggered mid-span by this wave.
The live `audit.log` (16k+ lines, legacy format) verifies TRUE under the
grandfathered rule both before and after the wave (verifier is strictly
backwards compatible). No CMP decision semantics, breaker, or grader
surface is touched.
