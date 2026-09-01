# ADR-004: Volatility Signal Producer (4th Source)

## Status
Accepted — implemented.

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
