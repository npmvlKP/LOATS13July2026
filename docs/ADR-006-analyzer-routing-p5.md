# ADR-006: Analyzer Routing Default OFF vs CMP P5 (F8-H-01)

**Status:** Accepted
**Date:** 2026-09-02
**Finding:** F8-H-01 (CMP Conformance, P5) — High conformance / Low capital safety

## Context

CMP phase gate P5 mandates, unconditionally: *"route ALL TradeDecisions to
Analyzer Mode."* The repository ships `Settings.analyzer_routing_enabled =
False` (`config/settings.py`), and `TradeDecisionEngine._do_route_or_disable`
terminates every decision in an audited `{"status": "disabled"}` outcome
when the flag is off.

The OFF default was itself a mandated safety correction: TODO-13 (HC-19)
removed the earlier default-ON **fabrication** — F7-H-01 documented
`analyzer_routing_enabled = True` returning a made-up
`{"status": "success", "analyzer_response": {"status":
"QUEUED_FOR_ANALYSIS"}}` after an `asyncio.sleep(0.1)` stub, with no HTTP
call. Turning the flag OFF by default killed that fabrication class.

F8-H-01 then observed the remaining gap: with routing off, the P5 2-week
forward test measures nothing, so the P5 gate stays open — a **documented,
deliberate deviation** from the unconditional P5 wording.

## Decision

1. **The production default stays OFF.** It is the runtime kill path
   (capital-safety direction) and the guard against default-on fabrication.
   Two gates enforce it: `scripts/verify_hc_registry.py` (AST check) and
   `scripts/fr7_health_check.py` HC-19. `ANALYZER_ROUTING_ENABLED=false` is
   documented in `.env.example`.

2. **Deviation recorded here (this ADR) and in README.** Until P5 closes,
   conformance reports cite this ADR as the tracking artifact.

3. **The closing step now exists and is runnable:**
   - `scripts/run_p5_forward_test.py` — supervisor that enables routing
     only for the supervised run (via `enable_analyzer_routing()`), runs
     the real `TradingSystem`, and appends a run log to
     `reports/p5_forward_test_<ts>.json`. Live runs require
     `--ack-live-endpoint`; `--dry-run` exercises the enable path without
     HTTP.
   - `scripts/verify_p5_forward_test.py` — grades run logs against the P5
     criteria: ≥14-day span, zero unhandled exceptions, routing enabled.
     Exit 0 iff PASS.

4. **Every routed decision now leaves a ROUTE audit row.** F8-H-01's
   Recommended Test (1) requires "an audit row with routing outcome exists
   per decision." Root-cause fix in `trade_decision.py`
   `_persist_routing_outcome`: the previous code probed for a nonexistent
   `db.async_record_trade_decision` (dead branch — only the private
   one-arg `_async_record_trade_decision` exists), so routing outcomes
   were never audited. The fix writes a dual-write (SQLite + JSONL,
   SHA-256-chained) `ROUTE` audit row via the canonical `async_log_audit`
   for **every** outcome — success, disabled, and error — and persists the
   `trade_decisions` row when missing (idempotent with the orchestrator's
   pre-persist).

5. **`get_decision_status` no longer fabricates.** It returned a hardcoded
   `{"status": "PROCESSED", "analyzer_status": "ANALYZED"}` mock for any
   id — the exact F7-H-01 fabrication class. It now reads the real
   `trade_decisions` row via `async_get_trade_decision` and returns
   `NOT_FOUND` for unknown ids.

## Consequences

- P5 remains formally open until the 2-week supervised run completes and
  `verify_p5_forward_test.py` grades PASS. TODO-25 evidence continues to
  record P5 as BLOCKED until that run starts; once it starts, the run log
  becomes the phase-gate evidence.
- `enable_analyzer_routing()` / `disable_analyzer_routing()` remain the
  runtime kill path, unchanged.
- Existing consumers of `get_decision_status` see `NOT_FOUND` for unknown
  ids and persisted statuses otherwise; the only observable behavior
  change is the removal of invented state.
- Latent-defect removal (ROUTE audit rows, real status) requires no
  config change and is covered by
  `tests/test_analyzer_routing_integration.py` +
  `tests/test_p5_forward_test.py` and graded by `scripts/eval_f8h01.py`.

## Verification Model (the F8-C-01 lesson)

Per ADR-005: a green gate is only evidence if the gate measures the thing
the mandate cares about. The eval harness `scripts/eval_f8h01.py` grades
the ten observable behaviors from the finding (before: 4/10 → after:
10/10), and the external verifier `scripts/verify_f8h01_external.py`
re-checks the same facts from a clean process without the test suite.
