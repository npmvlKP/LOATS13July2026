# P5 Resume Continuity + Backtest-Sanity Interval - Wave Record

**Date:** 2026-09-08 (Asia/Calcutta)
**Wave:** P5 grading prep (~13 days out): recover the abandoned F8-H-01
forward-test run, make resume safe against dual writers, and fix a latent
defect that made the P4 backtest-sanity gate unexecutable against the
production database.

## Findings addressed

1. **P5 evidence run abandoned (operational).** The live supervised run
   `reports/p5_forward_test_20260907_124455.json` (started 2026-09-07
   18:14 IST) was killed by machine teardown at 20:21 IST with no cleanup:
   `ended_at` stayed null, the daily status log flagged "no supervisor is
   writing to this run log", and the boot watchdog task `LOATS_P5_Resume`
   was found DISABLED, so nothing resumed it. The span clock only accrues
   while a supervisor samples; every idle day was a lost evidence day.

2. **Single-writer violation (design defect, fixed).** Resume eligibility
   checked only log shape (parseable, dry_run false, ended_at null) --
   never process liveness. With the watchdog re-enabled, a boot resume and
   an operator resume could both sample one run log, folding interleaved
   counter baselines into the graded MEASURED counters.

3. **Backtest-sanity hardcoded 5min interval (latent defect, fixed).**
   `run_backtest_sanity_check` fetched `interval="5min"` but the
   market-data task persists `settings.default_timeframe` (1min); the DB
   holds only 1min bars (evidence: `data/loats.db` historical_data groups:
   NIFTY/1min, TEST/1min). The weekly P4 exit gate therefore raised
   "No historical data found" on every real run. Discovered while
   exercising the F8-L-02 deterministic replay path for P5 prep.

## What was implemented

### Single-writer guard (scripts/run_p5_forward_test.py)

- `_process_image_path(pid)`: stdlib-only process-image lookup (Windows
  OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION) +
  QueryFullProcessImageNameW; POSIX /proc/<pid>/exe). Returns "" only for
  a nonexistent PID; a live-but-unreadable PID is distinct (fail closed).
- `_current_process_image()`: the comparator baseline MUST be the queried
  self image, not `sys.executable`. On this host the venv `python.exe` is
  a launcher whose process image is the base interpreter
  (`C:\Program Files\Python312\python.exe`); comparing against
  `sys.executable` classified every live writer as dead -- a fail-open bug
  in the exact guard meant to prevent dual writers. Verified empirically
  against the live supervisor PID.
- `_pid_alive_running_supervisor(pid)`: exact interpreter-image match
  (immune to PID reuse and to a different python.exe holding a recycled
  PID); unreadable-image PIDs count as live (fail closed); corrupt
  supervisor_pid fields degrade to "no writer" instead of crashing the
  resolver/status path.
- `_claim_run_log` / `_release_run_log`: compare-and-set claim recorded as
  `supervisor_pid` in the run log with persisted `resume_refusal` when a
  second writer is turned away; release happens only AFTER `ended_at` is
  durable (a release-first window would let a resume refuse a legitimately
  finished run). Release never resurrects `ended_at`.
- Wired into `_resolve_resume_target` (refusal reason printed, explicit
  target exits 2), `_init_run_log` (schema fields), `_run` (enforcement
  point before any baseline write), and `_status` (writer state + refusal
  surfacing).
- Negative-path proven live: a second `--resume` against the actively
  supervised log printed the guard refusal and exited 2; process audit
  (parent/child chain via CIM) confirmed exactly one writer.

### Interval source of truth (src/loats/backtest_sanity.py)

- New `interval: str | None = None` parameter; fetch uses
  `interval or settings.default_timeframe`. Scheduler path unchanged in
  shape; pinned callers can force a timeframe explicitly.
- RED-first tests (`tests/test_backtest_sanity.py::TestIntervalFromSettings`):
  default timeframe fetched (not 5min), explicit override wins, and an
  end-to-end 1min-bar run passing the 80% gate.

## Operational recovery performed (evidence, not code)

- Resumed the abandoned evidence run through the production wrapper
  (`C:\Users\npmvl-KP\loats-ops\p5_resume_wrapper.cmd`, detached) at
  ~12:27 IST; supervisor chain verified as launcher+interpreter pair on
  the claimed PID; cycles_completed climbing monotonically with fresh
  60s samples.
- Re-enabled `LOATS_P5_Resume` (state: Ready) -- now safe because a
  second writer is mechanically refused.
- Started OpenAlgo (127.0.0.1:5000) to restore the market-data substrate;
  LOATS->OpenAlgo HTTP and API-key auth verified live. Remaining blocker
  is broker-side: Zerodha session token expired ("Incorrect api_key or
  access_token" in openalgo errors.jsonl) -- requires an interactive
  broker re-login (operator action, deliberately not automated).
- Stray staged artifact `pytest-report.xmlcls` (junit XML written by an
  earlier `--junitxml=pytest-report.xml` invocation with a shell suffix
  glued on) unstaged and deleted; `.gitignore` rule widened to
  `pytest-report.xml*` so the suffix variant cannot stage again.

## Evidence

- Deterministic replay (F8-L-02 pin): `run_backtest_sanity_check`
  executed twice with `as_of_date=2026-09-04` produced identical analysis
  (73 windows / 748 bars / pass_rate 100) with the date stamped on the
  result; unpinned run grades INCOMPLETE-free live window (78 windows) and
  stamps as_of_date=None. Evidence JSON:
  `reports/p5_replay_exercise_<ts>.json` (gitignored).
- P5 supervisor status at wave close: ongoing, writer PID alive, span
  accruing, 0 unhandled exceptions.
- Gates: ruff/format/isort/flake8/mypy clean on all touched files; mypy
  fixed two pre-existing `scripts/` errors in the touched file (line 126
  Any-return; POSIX readlink typing). bandit CI scope (src/, B101 waived
  by config) clean; production-closure pip-audit: 48 packages, zero
  vulnerabilities after the ADR-0010 waiver; gitleaks clean at staging.

## Compatibility

- Run-log schema additions (`supervisor_pid`, `resume_refusal`) are
  optional keys; legacy logs grade unchanged (validator untouched).
- `run_backtest_sanity_check` gains an optional trailing parameter; all
  existing callers and call_args-based tests pass unmodified.
