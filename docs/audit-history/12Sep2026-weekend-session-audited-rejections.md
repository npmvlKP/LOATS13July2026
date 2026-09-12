# Weekend-Session Gate and Audited-Rejection Workflow (2026-09-12)

**Date:** 2026-09-12 (Asia/Calcutta). **Base:** `main` @ `3a1cd33`
(merge of PR #23). **Tree before wave:** clean, 407/407 tracked files.
Wave class: forensic discovery from live run evidence, root-cause fixes
behind RED-first nets.

## Discovery path (read-only forensics first)

The R8 queue was inventoried before any work: F8-L-01 (per-source
breakers) and F8-L-02 (`as_of_date`) were re-verified CLOSED at HEAD
(`per_source_breakers.py` + `tests/test_per_source_breakers.py`;
`as_of_date` propagation pinned by `tests/test_as_of_date_propagation.py`),
F8-L-03 was already DISCHARGED (04Sep, live-endpoint latency evidence),
F8-L-04/05/06 closed per the 07Sep reconciliation. The deferred-intake
thread (ADR-006 Am5) is config-complete; its remaining half is the
upstream gateway PR (marketcalls/openalgo #2047, all checks green,
awaiting maintainer merge - operator-gated, no repo action possible).

The forensic sweep then asked the standing question the P5 run's
`--status` output poses: **4,299 cycles with all-zero routing counters.**
Under ADR-006 Amendment 4's read-only semantic every routed decision
resolves as an honest `error` outcome, so zero across all three buckets
means zero decisions ever formed - either honest decision scarcity or a
recurrence of the Amendment 2 starvation class. Read-only probes:

1. `trade_decisions` since run start (2026-09-10T13:44:27Z): **0 rows**.
   17,286 signals persisted; 529 `REJECT`/`signal_batch` audit rows
   (in-run window; 523 by the 05:55Z snapshot, growing at ~8/minute);
   last decision ever: 2026-09-09 (a prior run).
2. Every rejection: `insufficient_source_diversity`,
   diversity_score = 0.428571... = **3/7 < 0.5** - only three of seven
   `StrengthSource`s survive per cycle.
3. Per-source signal census since run start: `volatility` 4,550 /
   `price_action` 4,500 / `ta` 4,436 / `options_flow` 3,795 (all
   pre-Saturday) / `sentiment` 51 / **market_data 0** (by design: it
   persists quotes/positions/funds/VIX, not signals). Saturday ran with
   three producers (sentiment ~1% of cycles), hence 3/7 forever.
4. Day-over-day: options_flow 5,234 (Wed) -> 2,379 (Fri) -> **0 (Sat)**.
5. `run_p5_forward_test.py --status` live: writer PID 18904 alive,
   span 1.67d, zero exceptions.

### Finding D1 (defect): weekday-blind session gate

`CMPRulesEngine.get_current_session` bucketed IST time-of-day without a
weekday check, so weekend 09:15-15:15 IST resolved `REGULAR` and the
full CMP decision funnel ran on non-trading days. Observed live: 529
signal-batch REJECT rows on Saturday 2026-09-12 and thousands of
weekend cycles accruing in the supervised run. The full day-by-day
decision history (111-268/day through 04-07 Sep) includes the same
weekend pollution.

Fix (`src/loats/rules.py`): `TradingSession.CLOSED` added; after IST
conversion, `ist_time.weekday() >= 5` returns `CLOSED` before the
intraday buckets. The weekday check runs on the IST datetime, so a UTC
weekend instant already inside an IST weekday resolves through that
weekday's buckets. `is_trading_allowed()` semantics are unchanged
(`== REGULAR`), so both consumers - the orchestrator's CMP entry gate
and `apply_gating_rules` - inherit the fix with no call-site edits.
`is_trading_allowed_at(instant)` added for wall-clock-independent
evaluation (tests/backtests).

Behavior note: this is the mandated direction of correction (CMP gates
trading to live sessions); the only observable change removes
non-trading-day processing. The pre-existing
`test_session_detection_all_buckets` "night" fixture (UTC Sunday 20:30)
was pinned against the incomplete behavior and is re-dated to a Thursday
UTC instant with identical asserted outcome.

### Finding D2 (defect): rejections past Step 1 were unaudited

`TradeDecisionEngine.create_trade_decision` audited only Step 1
(signal validation) while Steps 2-5 returned silent result dicts.
Consequence: during Friday 2026-09-11's live session, 1,024
`gating_rules_failed` and 3,948 `insufficient_strength` rejections
(supervisor log) were invisible in the audit trail - the database
showed a healthy-but-decisionless funnel while the truth lived only in
logs. This audit asymmetry directly masked the funnel's state during
the P5 evidence window.

Fix (`src/loats/trade_decision.py`): uniform `REJECT`/`signal_batch`
rows for every workflow step via the new `_audit_rejection` helper -
dual-write (SQLite + JSONL, SHA-256-chained) through the canonical
`db.async_log_audit`, best-effort (an audit-store failure is logged and
never cascades), test-environment-guarded (hermetic suite), metadata
shape `{"step", "reason", "details", **extras}` with Step 1 keeping its
`excluded_unknown_sources` diagnostic. Step labels:
`signal_validation`, `composite_strength`, `gating_rules`,
`position_limits`, `position_sizing`.

### Finding D3 (test gap): no weekend pin existed

The session test suite pinned intraday buckets only. Added
`test_weekend_market_closed_all_ist_day` (seven UTC instants x Sat/Sun,
including all three previously-REGULAR buckets),
`test_utc_weekend_instant_resolved_by_ist_weekday`, and
`test_is_trading_allowed_at_explicit_instant`.

### Finding D4 (verified benign): Saturday options_flow silence

The producer's one-sided/illiquid degrade (no contract rows to score on
a closed market -> emit nothing rather than fabricate) is the ADR-005
producer contract working as designed. Zero code change; recorded so
the Monday reopen (four producers persisting, 4/7 = 0.571 diversity)
is predictable in the audit trail.

## P5 run disposition (no run contact)

The ongoing supervised run (writer PID 18904, span 1.67d, zero
exceptions) was NOT stopped, resumed, or written to. The weekend-cycle
cycles it accrued are honestly counted but weightless for P5
decisional purposes. Per the Amendment 2 precedent, a structurally
starved run is restarted only after fixes are live; the restart is an
operator decision (kill supervisor task, terminate the log explicitly,
fresh `--ack-live-endpoint` start) because it resets the 14-day clock.
Monday 09:15 IST reopen is the natural decision point: if decisions
flow at 4/7 diversity, the span may stand with its weekend gap visible
in the run log; if Friday's silent-stall class reappears, restart
under the fixed gate. Both ADR-006 and the operator runbook govern.

## Changes

- `src/loats/rules.py`: `TradingSession.CLOSED`; IST-weekend guard in
  `get_current_session` (docstring + inline rationale); new
  `is_trading_allowed_at(instant)`.
- `src/loats/trade_decision.py`: `_audit_rejection` helper; Steps 1-5
  now write uniform best-effort REJECT audit rows.
- `tests/test_rules_engine.py`: night fixture re-dated to a weekday UTC
  instant (same asserted outcome); three new weekend/session pins.
- `tests/test_trade_decision.py`: `TestRejectionAuditRows` (7 cases)
  pinning per-step rows, row shape, no-row-on-create, and the
  never-cascades contract.
- `scripts/ratchet_baseline.py`: ceiling 407 -> 408 (+1 wave record),
  history annotated.

## Verification (measured values; RED-first)

RED (pre-implementation): 9 new tests failed for exactly the diagnosed
missing capabilities (`TradingSession.CLOSED` absent x3, audit rows
absent x5) with one created-path fixture initially mis-designed and
corrected before implementation; all 43 pre-existing pins in the two
files stayed green through RED. GREEN (post-implementation): 52/52 in
the two files. Full-suite and gate results recorded below from the
frozen-tree runs.

## Consequences

- Weekend market hours produce CLOSED sessions end-to-end: no CMP
  funnel, no REJECT-row noise, no weekend cycles reaching the decision
  path on the next non-trading day. History interpretation note: prior
  audit-history per-day decision counts include weekend rows; treat
  pre-fix weekday-of-week distributions accordingly.
- Every future rejection is attributable in the audit trail by step,
  closing the observability gap that hid Friday's stall class. Audit
  volume grows by one row per rejected batch (Saturday volume
  disappears entirely under D1).
- New Settings fields: none. New env vars: none.
