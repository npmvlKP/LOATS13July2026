# 29Sep2026 — F9-M-01-R2 chain re-anchor (25Sep frozen writer) + repair-tool backup-fidelity finding (R-15)

Session window: 29Sep 19:09–22:40 IST. Preceded by PR #109 (R-14 fix,
merge da3f0e9, 17:51 IST) and the #104–#108 paste-collapse AM wave.
Supersedes nothing; extends `24Sep2026-f9m01-r1-frozen-chain-head-resolution.md`.

## 1. R-14 runtime verification (the discharge criterion) — VERIFIED

The 13:37 IST paste asserted the restart would ride the LOATS_P5_Resume
task: FALSE at probe time — that task is DISABLED (last ran 26Sep); the
active keeper-alive is LOATS_P5_Watchdog (every 5 min, revive-only). A
healthy supervisor never picks up new code, so generation 11 (started
08:13 IST) still ran pre-#109 code in memory. The editable install
(`_editable_impl_loats13july2026.pth -> src`) was confirmed first, then
gen11 was soft-stopped via `p5_soft_stop.ps1` (CTRL_BREAK to the hidden
console; clean drain 2m48s: "Trading system shutdown complete" →
"Disabled Analyzer routing").

Like-for-like evening windows (13:40–14:10Z), sentiment budget-warning
durations parsed from `logs/loats.log*` (json.loads per line, `event`
key):

| window                       | n   | median   | max       | over-window (>8.1s) |
|------------------------------|-----|----------|-----------|---------------------|
| 28Sep gen11 (pre-fix)        | 211 | 8000.8ms | 12682.6ms | 78 (37%)            |
| 29Sep gen11 (pre-fix)        | 307 | 8007.5ms | 12610.0ms | 130 (42%)           |
| 29Sep gen12 (post-fix)       | 73  | 7988.4ms | 9874.0ms  | 10 (14%)            |

Gen12's 10 over-window events were ALL cold-start: confined to
13:48:38–13:52:06Z (first 214s after resume; empty caches). Steady
state from 13:52:06Z: pins-only (7950–8100ms), ZERO over-window events
through end of generation (13:52→14:11Z, plus gen13 steady state re-verified
through 14:30Z). Max 9.87s is the DESIGNED worst case, not a bounds
breach: per-feed budget 7.0s + fetch-timeout tail 3.0s = 10s ceiling
(docstring, `sentiment.py:217-222`), cancelled by the 8s window with
partial retention.

Persist truth (`data/loats.db.signals`, `metadata LIKE '%sentiment%'`):
380 rows persisted at >=13:48Z, freshest 13:58:25Z — persist continued
DURING the warning window (partial retention working as designed).

VERDICT: R-14 VERIFIED at 29Sep evening — steady-state cancellation
enforces at the window, sentiment survives restart, over-window maxima
eliminated outside the designed cold-start tail. Register row advanced
same-day. A full REGULAR-hours session (09:15–15:30 IST, 30Sep) re-runs
the same probes as the standing confirmation.

## 2. The 24Sep span closes; a NEW span starts (clock reset, recorded)

The graceful stop legitimately ENDED the 24Sep span
(`p5_forward_test_20260924_080208.json`, `ended_at 13:45:49Z`, 11 writer
generations, kill-switch PASS every generation, 3698 cycles). The
watchdog then correctly fresh-started:
`p5_forward_test_20260929_134805.json` (13:48:05Z). The 14-day
accumulation clock therefore RESETS to 13:48:05Z 29Sep; the prior span
holds 5d13h of continuous counter/carrier evidence and closes
incomplete-by-design on duration. Grade the NEW span for the P5 gate.

## 3. F9-M-01-R2: the 25Sep frozen-writer damage, characterized and re-anchored

Boot-time CRITICAL (first seen 25SepT21:30Z, recurring every generation
start through 29Sep): broken hash-chain link on entry
`audit_20260925090033366721_2093606120736` (expected
`92af1e6d…`, found `4cd92bc4…`). Post-repair NEW damage (the 24Sep
repair fixed the earlier 18Sep-entry freeze).

Forensics (dry-run + full walk of the pre-repair log):

- 20,803 entries; 398 broken links; 1 frozen run.
- Damage window: 25Sep 09:00:33–09:59:56 IST ONLY (entry timestamps);
  last broken entry at line 20533; every entry from 25Sep 10:00 IST
  onward linked correctly — the frozen writer lifetime ended that
  morning; zero damage accumulated in the 4+ days since (two dry-runs
  ~10 min apart both read 398).
- Interleaved shape: 398 frozen-link entries from ONE writer lifetime
  (`trade_decision_engine` REJECT/ROUTE stream) alternate with 270
  correctly-linked entries from a second writer lifetime in the same
  minutes — consistent with the two-writer-pool class documented in
  `sqlite-transaction-hygiene.md`. Both writer paths advance the shared
  `_chain_head` cache today (`database.py:1040`,
  `database_async_additions.py:580`); no live code path freezes.
- All 668 span entries re-verified self-hash before mutation; all
  broken links pointed at existing hashes (fail-closed pre-flight PASS).

Apply (pre-conditions all green: watchdog disabled and read back,
no supervisor alive, audit file byte-stable across a 10s window):

- JSONL re-anchored: 668 entries (lines 20135–20802).
- DB mirror: 668/668 updated, 0 orphans.
- REPAIR record appended to chain and DB.
- Tool replay verify: PASS. Independent walk: 20,804 lines, 0 broken.
- Production verifier `Database.verify_audit_log_integrity()`: PASS
  (repo venv, fresh process).
- Production-writer head-advance proof (24Sep lesson 4 standard):
  `Database.log_audit` TEST probe from a fresh process appended line
  20,805 — walk still 0 broken.

Backups: `audit.log.f9m01r1-backup.20260924-preserved` +
`loats.db.f9m01r1-backup.20260924-preserved` (24Sep era, preserved
BEFORE this apply because the tool's fixed backup names overwrite);
29Sep-era `*.f9m01r1-backup` pair written by this apply. See §4 for the
backup-fidelity caveat that applies to BOTH JSONL backups.

## 4. R-15 (NEW finding, P1): repair tool wrote repaired content as its "backup"

The 29Sep apply exposed it: the tool's JSONL "backup" had byte size =
repaired file minus REPAIR record, and a link-walk of the backup found
ZERO broken links. Root cause (c588be7, original): `main()` called
`reanchor_span(entries, …)` — which mutates the list in place — BEFORE
`write_repaired_log()` serialized that same list to
`*.f9m01r1-backup`. The docstring's "Snapshots the audit log before
mutating" was true only for the SQLite leg (genuine: snapshotted before
`repair_db`). Both real runs (24Sep, 29Sep) therefore hold repaired
content, not pre-repair state, in their JSONL backups. The pre-repair
state remains reconstructible for 29Sep (DB backup is pre-repair and
0 file-only orphans existed); for 24Sep the DB-era backup is likewise
genuine.

Fix shipped same session (F9-M-01-R2): backup is serialized from the
PRE-repair list before `reanchor_span` runs; `write_repaired_log` no
longer writes the backup; the REPAIR record's hardcoded "23 frozen
runs" reason string now reports the actual run/link counts; module
docstring corrected. Pinned by `tests/test_repair_backup_fidelity.py`
(4 tests: backup holds pre-repair broken link and no REPAIR record;
backup re-derives the repaired hashes; DB backup holds the pre-repair
hash; dry-run writes nothing). RED proven before the fix (2 fidelity
tests failed against c588be7), GREEN after.

Classification: R-15 P1 (evidence-integrity tooling; no production
trail corrupted — the live chain was repaired correctly both times;
only the restore artifact was degraded).

## 5. Ops-state changes made this session

- LOATS_P5_Watchdog: disabled for the apply window, RE-ENABLED (read
  back Ready). Gen13 (PID 9584) fresh-started the new span at 19:48 IST.
- 24Sep-era backups preserved under dated names (see §3).
- Span governance note for future sessions: a HEALTHY supervisor is
  never restarted by the watchdog; picking up merged code requires the
  soft-stop path, and a graceful stop CLOSES the running span (fresh
  span, day-0 reset). Plan verification sessions accordingly.
