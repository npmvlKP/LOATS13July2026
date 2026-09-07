# F8-H-04 Closure Record

**Date:** 2026-09-07 · **Scope:** `docs/audit-history/01Sep2026-FR.md`
finding F8-H-04 (coverage floors weakened instead of met; FR floor map
restored, backtest_sanity / scheduler / alerts / strike_selection
lifted) · **Verdict:** CLOSED at HEAD `af37d33`, backed by a fresh
outcome-level verification run.

## Method

Repository evidence over narrative. The remediation itself landed in
the F8-H-03 stabilization wave, commit `7d6a16b` (2026-09-02,
in `main` ancestry): full FR floor map restored (alerts 80, scheduler
80, backtest_sanity 80, strike_selection 75 alongside the existing
six), `scripts/check_per_module_coverage.py` hardened fail-closed
against narrowing or missing data, targeted lift tests per module
(scheduler job-error / holiday / misfire edges, alerts failure and
broad-except paths, backtest_sanity walk-forward slicing / per-window
PnL / no-look-ahead, strike_selection strategy branches), and the
FR-prescribed anti-narrowing regression nets. This record adds what
the FR demanded and no prior wave supplied: a live outcome
verification at HEAD.

## Outcome evidence (2026-09-07, Windows 11, loatsNEW venv, HEAD `af37d33`)

Fresh CI-contract run (`pytest tests/ --cov=src --cov-branch
--cov-fail-under=80` with xml/json reports, commands identical to the
`ci.yml` pytest-coverage job): **1553 passed / 0 failed / 0 warnings,
290 s, aggregate coverage 87.33%** (floor 80). Floor gate
(`scripts/check_per_module_coverage.py`, FR fallback map) exit 0:

| Module | FR floor | At audit (01Sep) | At closure (07Sep) |
| --- | --- | --- | --- |
| backtest_sanity.py | 80 | 59.6% (red) | **85.5%** |
| scheduler.py | 80 | 74.3% | **89.5%** |
| alerts.py | 80 | 77.9% | **82.3%** |
| strike_selection.py | 75 | 74.6% | **87.0%** |
| orchestrator.py | 80 | 80.3% (zero margin) | **81.8%** |
| trailing_stop.py | 80 | met | 93.2% |
| trade_decision.py | 80 | met | 84.4% |
| options.py | 85 | met | 95.2% |
| database.py | 80 | met | 81.6% |
| database_async_additions.py | 80 | met | 80.9% |

Anti-narrowing guards live-pinned at HEAD by
`tests/test_coverage_floor_map.py`: the script's enforced map AND its
fail-closed fallback must both equal the FR-specified map frozen in
the test (module removed, extra module, or lowered floor all break
dict equality and fail CI).

## Disposition

F8-H-04 CLOSED. The 01Sep register's item 5 is discharged; no
remaining module sits at or near zero margin. The floor gate's green
state is reachable and wired (CI pytest-coverage job + pre-push
`per-module-coverage` hook), so any future narrowing or regression is
a visible CI failure, not silent drift.
