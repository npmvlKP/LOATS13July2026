# ADR-004: Volatility Signal Producer (4th Source)

## Status
Accepted — implemented.
**Amended 2026-09-01 (F8-C-01): see ADR-005 for the price_action producer
addendum and the corrected verification model.**

## Context
The CMP strategy requires a composite strength built from at least 3 unique
sources, but the diversity gate uses the full canonical source space (7
members) as the denominator. This makes 3 distinct sources yield 3/7 ≈ 0.429,
which is below the 0.5 floor and therefore rejected. Four distinct sources
yield 4/7 ≈ 0.571, which passes. This design intentionally raises the bar so
that the strategy is not driven by a narrow cluster of correlated producers.

Original baseline producers: technical analysis, sentiment, price action.
A 4th producer was needed to satisfy the diversity gate in production.

## Decision
Add a dedicated volatility-analysis signal producer that:
1. Runs inside the orchestrator's 80 ms parallel cycle window.
2. Uses existing TA primitives (ATR, VWAP) plus Hurst-exponent regime detection.
3. Emits signals tagged with `StrengthSource.VOLATILITY`.
4. Is persisted to the database via `db.async_create_signal(signal)`.
5. Runs alongside the VIX fetch in the market-data task so VIX is wired and
   the volatility producer is active every cycle.

## Consequences
- The orchestrator now produces 4 independent source types by default, so a
  live cycle can satisfy the diversity gate without extra configuration.
- If the volatility pipeline fails (no data, bad bars), the existing 3-source
  fallback is still below the gate and the CMP strategy will early-return,
  which is the safe default.
- The 4th producer adds CPU work within the parallel window; budgets are
  monitored and logged if exceeded.

## Verification
- `scripts/probe_hc15_strength_gate.py` confirms 3 sources rejected, 4 sources
  accepted.
- `tests/test_e2e_cmp_chain.py` confirms the orchestrator can produce a
  TradeDecision from 4 real signals including volatility.
- `scripts/verify_todo8_external.py` bundles all evidence.

## F8-C-01 Correction (2026-09-01)

The original Verification section above was **misleading at the time it was
written**: `tests/test_e2e_cmp_chain.py` (pre-2026-09-01) fabricated its
`Signal(...)` fixtures — including the `price_action` source the CMP baseline
required — and injected them into the DB past the producers. It validated the
gate, not the production emission set. The claim "the orchestrator now
produces 4 independent source types by default" was therefore unfounded:
production emitted only `{ta, sentiment, volatility}`, the diversity gate
evaluated 3/7 = 0.4286 < 0.5, and `create_trade_decision` rejected every
cycle (`insufficient_source_diversity`). The chain was dead in production
while all health checks were green (F8-C-01, 5th consecutive "chain dead"
review finding).

Remediation (Option A of F8-C-01):
1. A real `price_action` microstructure producer was added to the
   orchestrator (`_execute_price_action_analysis`), derived from data the
   orchestrator already fetches (Supertrend position, VWAP position,
   consecutive-candle momentum, candle-body ratio) — see ADR-005.
2. Scheduler-emitted signals now carry enum-valid `source` tags
   (`TECHNICAL_ANALYSIS` / `SENTIMENT`), closing the `"unknown"`-source
   batch-fatal rejection path.
3. `tests/test_e2e_cmp_chain.py` was rewritten to drive the REAL producer
   methods against fixture feeds (mocking only the OpenAlgo/RSS boundaries)
   and to assert on the stored signals' sources; a mutation check (removing
   the price_action emission site) makes the suite fail (verified: 5 tests
   fail under mutation, 12/12 pass when intact).
4. HC-15 now includes a production-side static check: the registry probe
   (`scripts/probe_hc15_strength_gate.py`) and the FR7 master
   (`scripts/fr7_health_check.py`) FAIL if `orchestrator.py` stops emitting
   any of the 4 required `StrengthSource` tags.

Lesson recorded: a verification loop that fabricates the producer output it
is supposed to verify is self-referential. Health checks must probe the
production emission set, not only the gate arithmetic.
