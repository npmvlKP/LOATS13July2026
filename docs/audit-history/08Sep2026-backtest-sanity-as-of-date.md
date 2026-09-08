# Backtest-Sanity as_of_date Pinning - Wave Record

**Date:** 2026-09-08 (Asia/Calcutta)
**Wave:** backtest_sanity consumes the F8-L-02 `as_of_date` seam (merged
PR #8, `3997e31`); removes the stale TODO-26 external verifier as the
first commit of the wave, as sequenced by the prior risk register.

## Root cause addressed

`run_backtest_sanity_check` anchored its history fetch window to
wall-clock `datetime.now(UTC)` on both ends. A replay of the same
analysis therefore queried a different, growing window on every run, and
neither the result model nor the audit log carried the snapshot date the
window was computed from - the exact gap the F8-L-02 closure record
(CMP Rule 8) closed for `TradeDecision`, now closed for walk-forward
sanity analysis.

Separately, `scripts/final_verify_todo26.py` had rotted: its section-10
check demanded `scripts/comprehensive_verify_todo26.py`, a file that
never existed in any commit of this repository's history (verified via
`git log --diff-filter=D`), so the verifier exited 1 (43/44 checks,
97.7%) on every run from a clean clone. It was a historical-wave
verifier, not a suite component - the full pytest suite was and is green
(1566 passed pre-wave). The hygiene test pinning its source
(`test_todo26_verifier_reads_archived_report`) and its pyproject
per-file-ignores row were removed with it.

Its companion probe `scripts/verify_todo26_external.py` was deleted in
the same wave: with the runner gone, the repo's own scripts-wiring guard
(`tests/test_scripts_wiring.py::TestLiveTree`) flagged it as an orphan
("cited by no live surface (only frozen archives)") - the deletion
exposed a latent dead-script dependency, and the guard caught it
in-suite. Its assertions (backtest_sanity exports, scheduler wiring
strings) are already enforced with strictly more rigor by
`tests/test_backtest_sanity_production.py`
(`test_required_exports_present`,
`test_scheduler_has_weekly_job_registration`), so removal loses no
coverage and satisfies the zero-duplicate-logic rule.

## What was implemented

| Surface | Change |
| --- | --- |
| `src/loats/backtest_sanity.py` | `run_backtest_sanity_check(..., as_of_date: date \| None = None)`. When supplied, the fetch window ends at the snapshot day's end-of-day (UTC, `23:59:59.999999`) so the day's bars are fully included and replays are deterministic; `cutoff_time = window_end - days_back`. `BacktestSanityResult` gains `as_of_date: date \| None` (default `None`); start and completion log extras carry the ISO value. `None` keeps the live wall-clock window (weekly scheduler path unchanged). |
| `tests/test_backtest_sanity.py` | `TestAsOfDatePinning` (4 tests): pinned EOD window bounds + `start = end - days_back`; `None` keeps live wall-clock bounds; result stamps the pinned date / `None`; same-date replays produce byte-identical query bounds. |
| `scripts/final_verify_todo26.py` | Deleted (stale historical-wave verifier; unsatisfiable check, see root cause). |
| `scripts/verify_todo26_external.py` | Deleted (orphaned after the runner deletion; assertions already enforced by `tests/test_backtest_sanity_production.py`). |
| `tests/test_repo_hygiene.py` | Removed `test_todo26_verifier_reads_archived_report` (asserted on the deleted runner's source). |
| `pyproject.toml` | Removed the deleted runner's per-file-ignores row. |

## Behaviour contract

- `run_backtest_sanity_check(symbol, days_back, window_size, step_size,
  as_of_date=date(2026, 9, 1))` fetches exactly
  `[2026-09-01 23:59:59.999999 UTC - days_back, 2026-09-01 23:59:59.999999 UTC]`
  and stamps `result.as_of_date == date(2026, 9, 1)`.
- Omitting `as_of_date` (scheduler default) leaves observable behaviour
  unchanged: live wall-clock window, `result.as_of_date is None`.
- No wall-clock date derivation was introduced; the zero-`date.today()`
  invariant across `src/loats` remains enforced in-suite by the
  F8-L-02 acceptance net.

## Verification state

- Targeted: `TestAsOfDatePinning` 4/4; backtest sanity files 42/42;
  hygiene suite green after the pin removal.
- Full suite: 1568 passed with `--cov=src --cov-branch
  --cov-fail-under=80` (CI-exact flags); per-module floors green
  (`backtest_sanity.py` floor 80).
- Gates: ruff check (repo scope) + ruff format + isort + flake8 +
  mypy `src/ --strict` + bandit `-r src/ -c pyproject.toml` +
  pip-audit (ADR-0010 waiver `PYSEC-2026-3740`) + gitleaks - all green.
- Scripts-wiring guard green on the live tree after the probe deletion.
- PR delivery through protected main followed this record; the
  post-merge `main` pipeline run **34188827522** completed
  successfully (2026-09-08) - attached as merge evidence per the
  PR #7 / PR #9 pattern.

## Risk register delta

- RESOLVED: `final_verify_todo26.py` stale reference (was item 2 of the
  prior register; consumed as this wave's first commit).
- RESOLVED: backtest_sanity consumes `as_of_date` (was item 4; its
  prerequisite - pinned snapshot dates via PR #8 - was merge-proven).
- NEXT: P5 grading ~21Sep (p5_forward_test_20260907_124455.json) -
  counters must show MEASURED routing activity; the pinned-window
  machinery delivered here is the replay substrate P5 grading runs on.
- NEXT: producer coverage 4/7 (F8-C-01); broker-side idempotency probe;
  eval re-run recommended before wave 4.
