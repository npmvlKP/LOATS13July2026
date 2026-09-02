# ADR-005: Price-Action Signal Producer (F8-C-01, Option A)

## Status
Accepted — implemented 2026-09-01.

## Context
F8-C-01 established that the CMP decision chain was unreachable in
production: the orchestrator emitted only three enum-tagged signal sources
(`ta`, `sentiment`, `volatility`) while `validate_signal_sources` requires a
diversity score of unique/7 ≥ 0.5 — i.e. at least 4 distinct sources. Every
production cycle was rejected with `insufficient_source_diversity`
(3/7 = 0.4286), so no `TradeDecision` could ever be created. The prior e2e
test fabricated the missing `price_action` signal, masking the defect, and
HC-15/HC-17 only exercised the gate math — both were green while the chain
was dead.

Additionally, scheduler-emitted signals carried no `source` key at all; any
scheduler signal inside the CMP 5-minute window resolved to `"unknown"` and
triggered the batch-fatal loud rejection (F8-M-01), hard-blocking the chain
on a schedule operators could not see.

## Decision
Implement Option A — a real fourth producer — rather than recalibrating the
diversity threshold (Option B). Rationale: the CMP baseline (ta + sentiment +
price_action) never had its price_action member built; weakening the gate to
3/7 would lower the correlation-risk bar the gate exists to enforce.

### 1. Orchestrator producer: `_execute_price_action_analysis`
- Runs inside the 80 ms parallel cycle window as a peer task of
  TA/sentiment/volatility/market-data (not cancelled on cycle timeout, since
  it is diversity-critical and must persist its signal).
- Data source: the OHLCV bars and quote the orchestrator already fetches —
  no new API surface, no rate-limit impact.
- Signal model (microstructure conviction):
  - **Direction**: agreement of Supertrend position and VWAP position of the
    last close (both above → BUY bias; both below → SELL bias; disagreement →
    NEUTRAL).
  - **Conviction**: consecutive same-direction candles ending at the newest
    bar (streak direction defined by the newest candle — a newest bar against
    the bias yields zero conviction) scaled with the 5-bar candle-body ratio
    (bodies dominating ranges = clean tape). Strength = 0.55 + conviction,
    capped at 0.85.
  - Emits `NEUTRAL` / 0.5 when references disagree or conviction is too weak.
- Tagged `StrengthSource.PRICE_ACTION.value`, persisted via
  `db.async_create_signal`, budgeted at 30 ms (warning above).

### 2. Scheduler source tagging
Scheduler `ta` and `sentiment` signal metadata now include
`"source": StrengthSource.TECHNICAL_ANALYSIS.value` /
`StrengthSource.SENTIMENT.value`. No scheduler signal can resolve to
`"unknown"`.

### 3. Consistency fix (root cause found during remediation)
`_execute_volatility_analysis` called `async_client.get_history` directly,
bypassing the `_safe_get_history` circuit-breaker wrapper used by every other
producer. It now uses `_safe_get_history`, restoring uniform
circuit-breaker protection and making the producer testable at the same
boundary as its peers.

### 4. Verification model (the F8-C-01 lesson)
- `tests/test_e2e_cmp_chain.py` rewritten: it drives the REAL producer methods
  against fixture feeds, mocking ONLY the OpenAlgo/RSS boundaries, and asserts
  on the persisted signals' sources before running the decision path. No
  fabricated `Signal(...)` is injected past a producer (the sole deliberate
  exception: a corruption probe injecting a bogus-source signal to prove the
  unknown-source gate still rejects).
- Mutation safety verified: removing the price_action emission site makes 5
  tests fail; intact code passes 12/12.
- HC-15 production-side check added to both `scripts/probe_hc15_strength_gate.py`
  (registry) and `scripts/fr7_health_check.py` (FR7 master): FAIL if
  `orchestrator.py` stops emitting any of the 4 required `StrengthSource`
  tags.

## Consequences
- Production emission set is now `{ta, sentiment, volatility, price_action}`
  → diversity 4/7 = 0.571 ≥ 0.5: a live cycle passes Step 1 of
  `create_trade_decision`.
- The full decision path (composite strength → gating → position limits → 2%
  sizing → trailing init → VaR → TradeDecision → Analyzer routing) is now
  reachable in production.
- The 4th producer adds one pandas window computation inside the parallel
  window (Supertrend + VWAP + a 5-bar scan); budget 30 ms, monitored.
- ADR-004's original Option-A claim is amended: the volatility producer
  filled the third slot, not the fourth; the CMP baseline price_action member
  is built by this ADR.
- Option B (recalibrating `diversity_threshold` to 3/7) is explicitly
  rejected: it would weaken the correlation-risk gate the CMP specifies.
