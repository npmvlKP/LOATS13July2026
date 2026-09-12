# Trade-Decision Persistence Coverage Wave (2026-09-13)

**Date:** 2026-09-13 (Asia/Calcutta, wave started 12 Sep ~23:30 IST). **Base:**
`main` @ `1465b04` (PR #27 merge). **Wave commit:** `5b927a8`
(fix) + this record. **Ceiling:** 410 held for the code delta
(append-only test file); 410 -> 411 re-pinned in the same commit as this
record.

## What was found (verification first)

The R7 round targeted the db-module coverage floor margins (per the
12Sep standing-risk-discharge record: `database_async_additions.py`
81.78% / `database.py` 81.88% vs floor 80 — margins so thin that modest
new code trips the gate). Scoping the uncovered blocks exposed
something worse than thin margins: the entire trade-decision persistence
layer carried **zero test references** — sync CRUD
(`database.py:1947-2179`: create/get/list/update-status/row-mapper) and
the aiosqlite-backed `_async_record_trade_decision`
(`database_async_additions.py:342-401`, 58 uncovered lines).

## Real defects fixed (born-RED evidence)

1. **`async_create_trade_decision` dispatched to a name that is never
   registered.** The wrapper called `self._async_create_trade_decision`;
   the extension's `method_map` binds `_async_record_trade_decision`.
   With the pool attached (production P5 writer after
   `async_initialize`), every trade-decision persist raised
   `AttributeError`, was swallowed by the broad fallback handler, logged
   a spurious "falling back" warning, and took the thread-offloaded sync
   path. The 58-line optimized implementation was provably dead code —
   the born-never-wired class. RED leg: the new dispatch pin failed
   exactly as predicted on the pre-fix tree.
2. **`async_log_audit` never consulted the pool at all** (a bare
   `to_thread` wrapper), while `ASYNC_DISPATCH_DOCUMENTATION.md` lists
   `_async_log_audit` as a primary true-async method — the documented
   tri-modal dispatch contract was violated and the 88-line dual-write
   implementation (JSONL-first, DB commit aborted on JSONL failure,
   sha-chained) was unreachable. RED leg: the dispatch spy test failed
   on the pre-fix tree (flag never set).

Both fixes dispatch to the registered names with fallback preserved, so
an audit record can never be lost to a pooled-path failure.

**Class sweep:** every remaining pooled dispatch site
(`_async_create_signal`, `_async_store_historical_data`,
`_async_store_quote`, `_async_store_position`, `_async_store_funds`, the
update/get families) targets a registered name — these two were the only
never-wired members. `_async_get_historical_data` is
registered-but-undispatched and absent from the documented primary list
(no contract violated; noted, untouched).

## Tests added (11, in `tests/test_database_async_additions.py`)

Sync CRUD: full-column round trip (Decimal-exact assertions,
timezone-aware pinned timestamps, F8-L-02 `as_of_date` snapshot),
missing-id -> None, NULL-JSON-column guards, all four
`get_trade_decisions` WHERE shapes, status update + CREATE/UPDATE audit
dual-write + missing-id False. Async: pooled create round trip via
aiosqlite, unpooled fallback persistence, dispatch pins (source-level
for the create wrapper, monkeypatched spy for the audit dispatch), and
the dual-write audit behavior (JSONL row + sha256 chain verification).

Determinism: seeded decision ids, `datetime(2026, 9, 12, 9, 15, 0,
tzinfo=UTC)` timestamps, `Decimal(str(...))` comparisons on read-back.

## Measured evidence (repo venv first on PATH, live)

| metric | baseline @ `1465b04` (live run tonight) | post-wave HEAD (live run tonight) |
|---|---|---|
| tests | 1794 passed | **1805 passed** |
| aggregate branch coverage | 88.25% | **88.74%** |
| `database.py` (full suite) | 82% | **85%** |
| `database_async_additions.py` (full suite) | 82% | **88%** |

Static gates at HEAD: ruff check (src/tests/scripts) 0, ruff format 0,
flake8 (src/) 0, mypy `src/ --strict` 0 (38 files), bandit `-r src/` 0.
Full-suite rc=0 with `--cov-fail-under=80`; per-module floors unchanged
and green. RED leg (pre-fix): 2 failed / 35 passed; GREEN leg (post-fix,
final pin set): 37/37 rc=0.

## R7 disposition

`database.py` 85% (margin +5.0 vs floor 80) and
`database_async_additions.py` 88% (margin +8.0): the thin-margin risk is
substantially discharged — the floors now sit on a layer with genuine
behavioral coverage, not bare proximity. R6 (nltk waiver) re-verified
live in the same sweep: nltk 3.10.3 still latest on PyPI, safety 3.8.1
still pins `nltk>=3.9`, installed tree matches — both ADR-0010 removal
triggers remain UNLIFTED, waiver stays required and current.

## Operational note

Mid-wave, the uncommitted working-tree delta vanished once (tree reset
to `1465b04` by an actor outside this session; no reflog trace, no
stash). The wave was recovered byte-identically from pre-commit's
stash-restore patch (`patch1789238153-35260`, snapshotted to
`%LOCALAPPDATA%/Temp/r7_recovery.patch` before application), re-verified
(37/37 rc=0, format clean), committed, and the authoritative full-suite
run had already validated the identical content (1805 passed / 88.74%
with the changes in tree). Lesson recorded in the quality-gates skill:
never run the commit-msg probe with uncommitted wave work in the tree
beside a concurrently-active session in the same checkout — stage or
commit first, probe after.
