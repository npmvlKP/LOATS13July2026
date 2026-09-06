# ADR-0007: Producer-Window Cancellation Semantics (F8-M-02)

## Status

Accepted — 2026-09-03

## Context

F8-M-02 reported that the 80ms parallel-producer window in
`TradingOrchestrator._execute_trading_cycle` cancelled only
`[ta_task, sentiment_task, market_data_task]` on `TimeoutError`, leaving
`volatility_task` (and `price_action_task`) to run past the window, with the
working tree comment claiming this was a deliberate F8-C-01 diversity
safeguard ("producers must persist their signals past the budget window").

Reverse-engineering the actual asyncio semantics (probed empirically on the
project venv, CPython 3.12.7) falsified the documented rationale:

- On timeout, `asyncio.wait_for` cancels the `gather`; gather cancellation
  propagates to **all** children. No producer ever outlived the window on
  the timeout path — the "exemption" was dead code.
- On the **producer-raises** path, `gather` does NOT cancel surviving
  children. There the F8-C-01 comment masked a real leak: a producer hung
  on a never-completing await keeps running across cycles and its late
  signal can land in a later window — the exact failure F8-M-02 describes,
  reachable through the exception path rather than the timeout path.

Diversity (F8-C-01) is a Step-1 gate property of the *stored signal set*
(producers persist signals before the window closes; verified by
`verify_f8c01_external.py` checks 2-4), not a producer-lifetime property.
No diversity requirement is affected by cancelling producers at window
boundary.

## Decision

1. Derive the producer set once (`producers` tuple passed to `gather`) and
   cancel every still-pending producer at **both** boundaries:
   - the `TimeoutError` branch (making "timed out" imply "producers stopped"),
   - the `except Exception` branch (closing the real leak: gather does not
     cancel survivors when a producer raises).
2. Factor the loop into module-level `_cancel_pending_producers()` (cancel
   is a no-op on done/cancelled tasks; the tuple also keeps strong task
   references for the cycle's lifetime — F6-H-05.3 GC-hazard class).
3. Re-anchor the stale `verify_f8c01_external.py` check 5: F8-H-03 retired
   scheduler signal jobs, so its grep for scheduler source tags could never
   pass again. The check now asserts the single-engine invariant directly:
   zero signal-emission tokens in `scheduler.py` plus the full 4-enum
   production source set in `orchestrator.py`.

## Consequences

- "Timed out" ⇒ "producers stopped" holds on every exit path; unbounded
  task lifetime under repeated hangs is eliminated.
- Observable behaviour on the timeout path is unchanged (gather propagation
  already cancelled everything); the exception path changes from
  "survivors leak" to "survivors cancelled", which is the defect fix.
- Regression tests in `tests/test_orchestrator_extra.py::
  TestProducerWindowLifecycle` prove the leak on the pre-fix tree
  (RED) and its absence on the fixed tree (GREEN), using a
  `create_task` spy to assert on the exact producer handles without
  loop-tick races.

## Amendment (2026-09-03, Remaining-Risk review): settle, don't fire-and-cancel

The original `_cancel_pending_producers` requested cancellation without
awaiting it, leaving a residual risk: a producer whose ``finally`` block
ran slow cleanup could still be executing when the next cycle tick began.
The helper is upgraded to `async def _settle_cancelled_producers`:

1. Cancel all pending producers, then `asyncio.wait(pending, timeout=0.05)`
   — a **bounded 50 ms grace** (half the 100 ms cycle budget) so a hung
   cleanup can never compound one hung fetch into a hung engine; a grace
   expiry logs a CRITICAL diagnostic naming the abandoned tasks.
2. Retrieve exceptions of finished, non-cancelled producers so a
   concurrently-failed sibling never surfaces as "exception was never
   retrieved" GC noise (the first error is re-raised by the enclosing
   gather; the rest are observed here).

Trade-off recorded: the settle can cost up to 50 ms inside the exception /
timeout boundary, but only when producers are actually mid-cleanup — the
fast path (all producers done) returns immediately. Cycle liveness is
ranked above cleanup completeness; telemetry covers the gap.

