# ADR 0005: Retire Scheduler Signal-Emitting Jobs (F8-H-03)

## Status

Accepted — 2026-09-02

## Context

TODO-19 retired the orchestrator's legacy signal combiner ("_execute_signal_generation")
and replaced it with independent analysis producers inside the 100 ms trading
cycle (``_execute_ta_analysis``, ``_execute_sentiment_analysis``,
``_execute_volatility_analysis``, ``_execute_price_action_analysis``).  However,
the APScheduler-based ``TradingScheduler`` kept its own ``ta_scan`` (1 min) and
``sentiment_scan`` (5 min) jobs that also created ``Signal`` records and wrote
them to the same SQLite ``signals`` table.

This produced two independent signal engines with the same tagging convention:

- Orchestrator: emits signals every 100 ms cycle, persisted via
  ``db.async_create_signal``.
- Scheduler: emits TA/sentiment signals on its own clock, persisted via the same
  table.

Both engines tagged signals with ``StrengthSource.TECHNICAL_ANALYSIS.value`` and
``StrengthSource.SENTIMENT.value`` respectively, so the window read by
``async_get_latest_signals(symbol, limit=10)`` could contain duplicate sources.
The CMP validator requires **≥3 unique sources** and a diversity score ≥ 0.5.
Duplicate sources in the 10-signal window reduce unique-source count and can
push the window below the gate, causing intermittent, schedule-correlated
lockouts.

Two options were considered:

- **Option A**: Make the scheduler the canonical producer and retire the
  orchestrator's TA/sentiment producers.
- **Option B**: Delete the scheduler's signal-emitting jobs and keep the
  orchestrator as the sole engine of record.

## Decision

**Option B** was selected.

Rationale:

1. **Latency architecture**: The orchestrator owns the <100 ms trading cycle and
   already runs all analysis producers in parallel.  Moving canonical production
   to the scheduler would break the cycle-time guarantee and add APScheduler
   jitter to the signal path.
2. **Source diversity**: The orchestrator already produces four distinct
   sources (TA, sentiment, volatility, price-action).  The scheduler only
   produced two of them, so the scheduler could not satisfy the diversity gate
   on its own without the orchestrator anyway.
3. **Operational clarity**: Having one engine of record removes ambiguity about
   "which producer is the source of truth" and makes production debugging
   deterministic.
4. **Scheduler value retained**: The scheduler still performs essential support
   work — market-status checks, data cleanup, and the weekly backtest-sanity
   gate — so it is not removed.

## Consequences

- **Positive**: The CMP validator's window is now populated exclusively by the
  orchestrator's producers, eliminating duplicate-source contention and
  schedule-correlated lockouts.
- **Positive**: ``_market_status_check_task`` no longer dynamically adds or
  removes signal jobs; its only job is to log market state.
- **Positive**: ``run_once("ta_scan")`` and ``run_once("sentiment_scan")`` log a
  clear warning that the job is retired, preventing silent regressions if an
  operator or old script invokes them.
- **Negative**: Any external system that called ``run_once("ta_scan")`` or
  ``run_once("sentiment_scan")`` will now get a warning and no signal.  This is
  intentional: the orchestrator's cycle is the supported path.
- **Scope**: The ``Signal`` model, ``StrengthSource`` enum, ``resolve_source``,
  ``async_create_signal`` and ``async_get_latest_signals`` are unchanged.  Only
  the scheduling and job-management surface of ``scheduler.py`` was modified.

## Verification

- ``tests/test_signal_source_invariant.py`` — AST scan asserts every ``Signal``
  constructor in ``src/loats/`` (except DB row hydration and performance probes)
  tags a ``source`` key that resolves to a ``StrengthSource`` member.
- ``tests/test_scheduler.py`` and ``tests/test_scheduler_coverage.py`` updated to
  expect only the three support jobs (market_status_check, data_cleanup,
  backtest_sanity_check) and retired behavior for ta_scan / sentiment_scan.
- ``tests/test_e2e_cmp_chain.py`` already drives the real orchestrator producers
  end-to-end and continues to prove the CMP chain can reach a TradeDecision.

## References

- F8-H-03 issue description
- TODO-19 / F8-C-01 orchestrator producer consolidation
- ``src/loats/scheduler.py`` (post-change)
- ``src/loats/orchestrator.py`` producers: ``_execute_ta_analysis``,
  ``_execute_sentiment_analysis``, ``_execute_volatility_analysis``,
  ``_execute_price_action_analysis``
