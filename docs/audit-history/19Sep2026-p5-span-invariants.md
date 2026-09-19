# 19Sep2026 - P5 Span Invariants: Span-Attached Kill-Switch Proof, Market-Data Availability Evidence, PowerShell-Safe Evidence Battery (P5-OPS-01)

**Status:** LANDED (verification evidence below, all gates green)
**Scope:** `scripts/verify_p5_forward_test.py`, `scripts/run_p5_forward_test.py`, `tests/test_p5_f9c02_span_invariants.py` (new net, born-RED proven)
**Register items discharged:** P1 (H2/H7) kill-switch proof span-attachment; P3 operator-reported market-data service evidence; P3 19Sep evidence-battery PowerShell breakage.

## 1. Inputs (19Sep2026)

1. The 19Sep operator status snapshot: live run `p5_forward_test_20260916_140341.json`
   (started 2026-09-16T14:03:41Z, writer PID 19316 alive, 7109+ cycles measured,
   0 exceptions, verdict INCOMPLETE as expected mid-span) and the quality-gate
   battery whose ledger line `$fail += (($LASTEXITCODE -ne 1) * 2)` aborted
   PowerShell 5.1 with `NotADefinedOperationForType` (no `[bool] * [int]`
   operator), leaving `QUALITY_GATES_FAILURES=1` as the placeholder echo of the
   assignment text instead of a count.
2. The adversarial register P1: the run's sole `kill_switch_verified` event
   (19Sep 01:07Z) belongs to the FOURTH writer generation; generations 1..3
   (16Sep fresh start + the 16Sep and 17Sep resumes) carried no proof, so an
   ENDED artifact would have graded "clean since 16Sep" on the strength of a
   probe that only proved "clean under PID 19316 since 19Sep".
3. The operator's market-hours observation: the OpenAlgo analyzer surface
   (`http://127.0.0.1:5000/dashboard`, Zerodha NFO option-chain feeds behind it)
   served live data continuously 09:00-23:30 IST, and asked that the P5
   scenario "make suitable arrangements" for it.

## 2. Root causes

- **RC-1 (P1/H2/H7):** the F9-C-02 grader criterion
  (`_grade_kill_switch_evidence`) graded only the top-level
  `kill_switch_verified` / `kill_switch_active_at_start` fields - last-writer
  truth, not span truth. A resumed 14-day span therefore accumulated
  unprovable generations silently; nothing in the event stream was consulted.
- **RC-2 (market-data request):** the requested surface is an EXTERNAL process
  (OpenAlgo on `127.0.0.1:5000`; its `INFO in data` Zerodha logs are OpenAlgo's,
  not LOATS'). LOATS cannot attest another process's internals - only its own
  span-visible consequences (cycle activity, orchestrator state, per-source
  breaker fleet). Folding anything stronger would have fabricated evidence.
- **RC-3 (battery):** the documented gate battery used PowerShell boolean
  arithmetic (`($LASTEXITCODE -ne 1) * 2`) to weight a failure ledger; PS 5.1
  has no such operator, so the ledger died mid-session and the summary echoed
  unexpanded text. There was no supported, test-pinned composition helper.

## 3. Remediation

### 3.1 Grader: kill-switch proof is SPAN-attached (fail-closed)

`scripts/verify_p5_forward_test.py` gains the single-source generation model:

- `_span_kill_switch_generations(run_log)` re-derives writer generations from
  the event stream: every `writer_claimed` opens a generation; events BEFORE
  the first claim form the fresh-start generation (present only when such
  pre-claim events exist - exactly the live log's `routing_enabled` at
  14:03:46 before the 23:24:02 claim); `kill_switch_verified` proves its
  generation; `kill_switch_alarm` records `verified: false` (the probe RAN and
  failed - an unverifiable halt proves nothing).
- `_unproven_kill_switch_generations(generations)` lists holes.
- `grade_run_log` hard-FAILs an ENDED run with ANY unproven generation
  (`KILL-SWITCH PROOF IS NOT SPAN-ATTACHED (CMP P5 gate): writer generation(s)
  N..M lack the verification event ...`); an ONGOING run stays INCOMPLETE
  with the hole named, so the operator can close future generations by
  resuming (every resume probes and stamps since the F9-C-02 closure wave).

No schema change: existing logs grade from their event streams; legacy logs
without events keep the previous fail-closed criterion.

### 3.2 Supervisor: operator-visible invariants + honest availability fold

`scripts/run_p5_forward_test.py`:

- `_span_kill_switch_generations` / `_unproven_generations` DELEGATE to the
  validator module at call time (gate policy stays single-source; tests patch
  by name exactly like `collect_disabled_route_rows`).
- `_announce_span_invariants(run_log)` prints what the 30Sep checkpoint will
  grade - the generation hole (or `all writer generations verified`) plus the
  latest market-data availability disclosure - wired into `--status` and the
  supervised-loop exit.
- `_market_data_availability(system, live_cycles)` folds per sample:
  `cycle_activity_observed` (this sample's cycle delta > 0),
  `orchestrator_running`, and `sources` (per-source breaker fleet status).
  Any probe failure degrades to `{status: unverified, reason: ...}` - never a
  fake clean shape; a fold failure never aborts the sample. The grader treats
  the field as ANNOTATION-ONLY (NOTE lines), mirroring the outage-window
  disclosure discipline: a density hole is disclosed, never graded, never
  whitewashed.
- `_supervise_live` marks `ended_at` on the log the moment the supervised
  window ends (before `_run`'s finally), so recovery loops see the window
  close even if the process dies first; the clean path re-stamps
  authoritatively.
- `verify_exit_code_battery(*codes)` is the supported composition: pass gate
  exit codes as INTEGERS, receive the failure count (which doubles as the
  process exit code). Feeding it a session-line string raises immediately,
  naming the `[bool]*[int]` trap - the broken shape cannot pass through this
  surface silently again.

### 3.3 Span-safety statement (live run 20260916_140341 untouched)

All production edits are append-only/read-side. The live writer (PID 19316,
generation-3 code) keeps sampling; its log gains the new fields only from the
NEXT start/resume. Consequence, recorded honestly: because generations 1..3
can never retroactively carry proof, run 20260916_140341 is NOT eligible to
grade PASS as a whole-span artifact under the span-attached rule - exactly the
fail-closed outcome the register prescribes. The operator paths to a citable
P5 gate are (i) restart a fresh span (every future start/resume stamps proof
automatically; a fresh 14-day span from 01Oct gates ~15Oct), or (ii) an
explicit, documented operator acceptance of the pre-19Sep halt-path exposure.
The 30Sep checkpoint must cite this record when reading the run's verdict.

## 4. Verification evidence (all run 19Sep2026, loatsNEW venv)

- New net born-RED: `tests/test_p5_f9c02_span_invariants.py` 18 failed / 1
  passed before the production edits; 19/19 PASSED after
  (`pytest tests/test_p5_f9c02_span_invariants.py`, rc=0).
- Regression: 169 prior P5/F9-C-02/F9-M-03/F8-H-01/taint-exporter pins PASSED
  (test_p5_forward_test, test_p5_f9c02_kill_switch_and_archive,
  test_p5_f9c02_outage_window, test_p5_f9c02_routing_guard,
  test_f9m03_audited_attempt, test_f8h01_fixes,
  test_infinity_taint_exporter).
- Live `--status` (rc=0) announces:
  `[FAIL] kill-switch span proof: writer generation(s) 1..3 lack the
  verification event (CMP P5 gate); verdict will be INCOMPLETE unless the
  current writer records a verification event, and any resumed artifact will
  FAIL closed on the hole`.
- Live grader on the ongoing run (rc=1, INCOMPLETE): the span-attached reason
  names generation(s) 1..3; the outage NOTE and zero-decisional reasons are
  unchanged; data freshness 54s.
- Grader on the poisoned snapshot (rc=1, FAIL): ROUTING DIVERGENCE VOID
  preserved; the span-attached criterion adds its condemnation
  (generation(s) 1..6) without altering the archive record's citations.
- The live log correctly shows NO market-data availability disclosure yet
  (the running writer predates the fold) - nothing fabricated.

## 5. Citation rule

Cite this record for: the span-attached kill-switch criterion (CMP P5 gate),
the market-data availability evidence semantics (annotation-only,
never fabricated), and the PowerShell-safe battery composition. The 30Sep
grading checkpoint MUST read section 3.3 before citing run 20260916_140341.
