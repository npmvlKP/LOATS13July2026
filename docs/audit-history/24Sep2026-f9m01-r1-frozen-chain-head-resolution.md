# F9-M-01-R1 — Frozen Chain Head in the Pooled Async Audit Writer:
# Root Cause & Re-Anchor Resolution

**Finding:** Follow-up to F9-M-01 (TODO-6). The SHA-256 chain delivered in
d73536d (17Sep) is chained, but the live production log FAILS its own
verifier: `verify_audit_log_integrity()` returns **False** on
`data/audit.log` (18,682 entries), logging a CRITICAL broken-link alert on
entry `audit_20260918034517416986_1747918704320` and every boot and
scheduler integrity pass since 18Sep.

**Status:** RESOLVED 2026-09-24 (this wave). Root cause fixed in the
writer; live log re-anchored by the fail-closed repair tool; regression
pins added; full repo suite green.

## Root cause (code-pinned and live-proven)

`_async_log_audit` (the aiosqlite pool-path writer in
`src/loats/database_async_additions.py`) read the chain-head cache via
`_read_chain_head()` but **never called `_advance_chain_head()`** -- only
the canonical sync writer (database.py `_log_audit_inner`) did. The
resolution doc of 17Sep claimed the second writer "carries identical
chain semantics"; that claim was wrong and was never exercised by a
pooled-writer test (`test_audit_chain_f9m01.py` writes through the sync
path only).

The damage pattern in the live log proves the mechanics:

- 4,578 entries (lines 14082..18681) carry a `previous_hash` that does
  not match the previous line's `sha256_hash`;
- they form **23 consecutive frozen runs**, each linking to a hash that
  IS present in the file (0 exceptions) -- each run is one `Database`
  lifetime whose head cache froze at its first-read tail (the first,
  largest run: 3,207 entries frozen at `be01854c...`, the 18Sep 03:45 IST
  head);
- the log tail (post-23Sep-restart writer) chains correctly again, which
  is exactly what a fresh cache scan does.

Secondary latent defects found in the same writer and fixed in the same
wave (root-cause discipline; both were live):

1. `entry_id` was generated on the event loop with a microsecond
   timestamp + `id(self)` suffix -- same-microsecond concurrent writes
   collided on the UNIQUE key and mass-fell back to the sync path
   (observed 20+ fallback warnings in one gather). Sync-path parity:
   uuid4 suffix.
2. The JSONL append ran on the loop thread outside `_audit_lock` while
   the DB insert ran under `_async_write_lock` -- an interleaved fallback
   write orphaned the pooled line (file present, DB absent). Live
   counts: 113 file-only entries, 272 DB-only rows.

## Remediation (this wave)

1. **Writer fix (`database_async_additions.py`)**: the pooled write now
   runs as ONE `asyncio.to_thread` hop inside the shared `_audit_lock`:
   chain read -> hash -> JSONL append -> head advance (sync-writer
   parity) -> return; the aiosqlite INSERT then completes under
   `_async_write_lock` with the pool connection acquired across the
   hop. Sync and async writers serialize against each other; the head
   cache is always advanced. (An earlier draft that resolved the DB
   insert inside the worker deadlocked aiosqlite under contention -- the
   pool is single-threaded and awaits a loop that is blocked on the
   future; the delivered shape keeps all pool awaits on the loop.)
2. **Extracted `_scan_chain_head_uncached()`** in `database.py`: the
   file scan formerly inlined in `_read_chain_head()`; the uncached
   scan is the O(N) fallback primitive, the cached read stays O(1)
   (benchmark gate >50 inserts/sec preserved).
3. **`_audit_timestamp_ms()` parity helper** (timestamp_ms formula
   pinned against the sync writer).
4. **Regression pins (`tests/test_audit_chain_f9m01_async_writer.py`)**:
   9 tests -- pooled writes chain in file order, head cache advances
   (the exact seam), sync/async alternation forms one chain, 25-way
   concurrent gather intact, 40-way mixed-writer stress intact, DB rows
   mirror JSONL links, async-only chain verifies AND still fails a
   mutated middle entry, legacy grandfathering under async writes.
   RED-first: all failed on the pre-fix writer (plus a 25s hang on the
   25-way gather before the deadlock was understood).
5. **Re-anchor tool (`scripts/repair_f9m01_chain_head.py`)**: fail-closed
   (dry-run default; refuses on ANY self-hash mismatch, on any broken
   link pointing at a hash not present in the file, on mid-flight file
   changes; guarded per-row DB updates with rollback; snapshots both
   trails first). Chain semantics make link repair a RE-ANCHORING: the
   hash covers `previous_hash`, so fixing one link invalidates its
   self-hash and cascades to end-of-file -- the tool re-anchors from the
   first break to EOF and appends a dual-written REPAIR record pinning
   the SHA-256 of the pre-repair backup.

## Live repair evidence (2026-09-24)

- BEFORE: verifier False; 4,578 broken links across 23 frozen runs,
  span lines 14082..18681 of 18,682.
- Repair (validated end-to-end on byte-identical snapshots first, then
  applied to the live trail): 4,600 entries re-anchored; DB mirror
  4,578 rows updated, 22 file-only orphans left alone; REPAIR record
  appended; full replay PASS; **production
  `verify_audit_log_integrity()` now returns True**.
- Pre-repair backups: `data/audit.log.f9m01r1-backup`,
  `data/loats.db.f9m01r1-backup` (never git-tracked; data/ is
  ignored).

## Gates

- ruff check + format: clean (all touched files, repo-wide sweep green)
- flake8: clean; isort: clean
- mypy strict (pre-commit config): no issues on both touched modules
  and the script
- bandit: no findings
- gitleaks: no leaks (682 commits)
- Full suite: **2224 passed, 1 skipped, 0 failed** (412s, venv 3.12)
- Audit-adjacent suites: test_audit_chain_f9m01 (15) +
  test_audit_chain_f9m01_async_writer (9) + test_database +
  test_database_async_additions = 84 passed
- Coverage: CI-parity `scripts/verify_coverage_full.py`
  (run recorded in the 24Sep verification note)

## P5 span-safety statement

The audit WRITE path changes shape (single to_thread hop inside
`_audit_lock`), but audit call sites are unchanged: `async_log_audit`
keeps its signature, dispatch precedence, and fallback semantics; the
pool connection is acquired/released exactly once per successful call;
failures still raise after a JSONL-only write (documented file-only
failure mode, now also advancing the head like the sync path). The
running P5 forward test (started 24Sep 04:39 IST from the pre-fix
tree) is unaffected at runtime; it picks up the fix on its next
restart.
