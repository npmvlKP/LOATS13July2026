# 04Oct2026 — C-01: audit-chain integrity becomes a boot gate

## Finding

Audit finding C-01 (P0, integrity, confidence high): `TradingSystem.initialize`
logged a warning and continued when `async_verify_audit_log_integrity()`
returned False (`src/loats/main.py:59-60` pre-wave). CMP rule and register row
S-13 treat the SHA-256 chain as non-negotiable; the hash write itself was real
(`previous_hash` link chain, dual-write into SQLite — landed by F9-M-01 /
`5f634ba`, restored semantics per S-13). The defect was the CONSUMER: the
integrity check was observational, not a gate. A truncated or reordered
JSONL/SQLite chain could therefore still boot, trade-analyze, and append new
rows onto a broken head — the 7-year audit claim silently false after the
first failed verify, with later rows looking chained.

## Second instance of the same class (found during reverse-engineering)

`Scheduler._data_cleanup_task` (`src/loats/scheduler.py:392-394` pre-wave)
discarded the verifier's return value and then logged
`"Audit log integrity verified"` unconditionally — a false evidence line on
exactly the scheduled pass meant to certify the trail between boots.

## Verifier itself verified sound (no rewrite)

Per the audit-log review discipline, the verifier was probed before any
change: `Database.verify_audit_log_integrity` (`src/loats/database.py:2731`)
walks the JSONL in FILE ORDER with two layers — per-entry self-hash
re-computation over canonical serialization, plus the `previous_hash` chain
link across every entry carrying the key (legacy grandfathered entries
verified by self-hash; the head advances across the migration boundary
exactly as the writer computed it). Failures log CRITICAL naming the first
broken entry and return False. The full mutation matrix is already pinned by
the F9-M-01 test family (`tests/test_audit_chain_f9m01.py`,
`tests/test_audit_hash_mutation.py`, async-writer variant). Only the
consumers needed to change.

## Fix (wave `fix/c01-audit-integrity-boot-gate`)

1. `TradingSystem.initialize` (`src/loats/main.py`): a failed verification
   now raises `AuditIntegrityGateError` BEFORE the alerts, scheduler, and
   orchestrator legs start — a refusal needs no compensating teardown, and
   the broken chain can never carry new evidence rows. `main()` converts the
   raise into exit code 1 (the existing boot-failure contract).
2. Break-glass: `AUDIT_INTEGRITY_BREAK_GLASS` (Settings
   `audit_integrity_break_glass`, default **false**, `.env.example`
   documented) is the operator's TEMPORARY forensic continue for incident
   response. A break-glass boot sends an error alert, writes an
   `AUDIT_INTEGRITY_BREAK_GLASS` audit row (action/entity/user/metadata
   naming the override) onto the broken trail, logs at ERROR, and continues.
   Required follow-up: `scripts/repair_f9m01_chain_head.py` re-anchor, then a
   clean reboot with the flag off.
3. `ENVIRONMENT=test` skips the refusal (warning + continue) so test suites
   exercise all boot paths hermetically — the same skip convention as the
   R-08 duplicate-listener preflight.
4. `Scheduler._data_cleanup_task`: the verifier result is now graded — the
   `"Audit log integrity verified"` info line fires ONLY on a pass; a failed
   pass logs a loud ERROR naming the boot gate and the repair script.

## Tests (all new; file counts unchanged — zero ratchet impact)

- `tests/test_main_coverage.py`: the defect-pinning test
  (`test_trading_system_initialization_failed_audit_log` — asserted the
  warning-continue) replaced by the gate trio: production refusal (raises
  `AuditIntegrityGateError`, no break-glass audit row), break-glass continue
  (error alert + `AUDIT_INTEGRITY_BREAK_GLASS` audit row + all later boot
  legs run), `ENVIRONMENT=test` skip (continues).
- E2E (`TestC01AuditIntegrityBootGateEndToEnd`): the paste's acceptance test
  — seed one REAL chained entry via the actual writer, corrupt its stored
  self-hash in the JSONL, boot through the REAL verifier (unmocked gate,
  hermetic conftest Database): boot refuses, zero audit rows appended, and
  `start_orchestrator` never fires. RED-proven by construction against the
  pre-wave warning-continue behavior, which cannot raise.
- `tests/test_scheduler_full.py`: cleanup pass logs ERROR + never "verified"
  on a failed pass; "verified" fires only on a pass.
- `tests/test_config.py`: knob defaults false; `AUDIT_INTEGRITY_BREAK_GLASS`
  env mapping.

## Register surfaces (same wave, per the binding rules)

- R-20 row in `docs/RISK-REGISTER.md` (P2-fixed).
- S-17 row in `docs/CMP-SUPERSESSION-REGISTER.md` (SUPERSEDED) + the
  register test's row-count floor flipped 16 → 17 in the same wave.
- `.env.example` operator-surface entry for the break-glass knob.
