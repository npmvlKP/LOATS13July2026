# 02Oct2026 Wave: ADR-006 Amendment 8 — Host Decision-Telemetry Intake Recorded LIVE

## Mandate (operator, 02Oct2026 18:58 IST)

Operator quote from the routing-facts correction session: the repo's
"`analyze` intake returns 404 until a decision-intake route exists"
descriptions are stale relative to the deployed host; follow-up direction
to sync the repo docs with the host reality ("worth a docs-wave
amendment note if the operator wants repo docs synced with the deployed
host" — operator directed it).

## Live evidence gathered before writing (two-sided)

- Host checkout `G:/.OA/OpenAlgo` ships the decision-telemetry intake:
  `restx_api/analyze.py`, `POST /api/v1/analyze` ("Decision-telemetry
  intake endpoint", ADR-006 Amendment 5 counterpart; namespace mounted
  at `/analyze` in `restx_api/__init__.py`).
- LOATS `data/audit.log`: 95/95 ROUTE rows on 2026-10-01 carry
  `metadata.routing_outcome.status = "success"` with
  `analyzer_response.data.recorded = true`; rotated logs carry the
  matching "Routing TradeDecision to Analyzer" /
  "Successfully routed decision" event pairs (no analyzer-exception
  lines). Historical disabled rows (993) corroborate the off-state
  audited-`disabled` semantics.
- `reports/p5_forward_test_20260929_141804.json`: `routing.enabled_at_start
  = true` with the standing note that the production default remains
  OFF (routing enabled only for the supervised P5 run).

## What landed

- `docs/ADR-006-analyzer-routing-p5.md`: **Amendment 8** (newest-first)
  recording the live intake, the receipt evidence, unchanged
  audited-attempt semantics (Amendment 7), unchanged default-OFF
  routing (F8-H-01/HC-19), and the zero-behavior-change doc-sync scope.
- Present-tense 404-era prose re-dated as history in:
  `src/loats/config/settings.py` (Amendment 5 comment block +
  `analyzer_intake_path` field description), `src/loats/openalgo.py`
  (breaker-isolation + per-call resolution comments),
  `src/loats/trade_decision.py` (audited-attempt counter comment).
- Amendment-5-era test docstrings synced:
  `tests/test_analyzer_intake_contract.py` (module docstring + pin 2),
  `tests/test_analyzer_breaker_isolation.py` (docstring pin 5 + test
  docstring). All assertions untouched.
- `scripts/ratchet_baseline.py`: ceiling 519 -> 520 (this wave record),
  history entry appended (single atomic edit with the constant flip).

## Verification

- Two-sided grep: no present-tense "404s it by design" / "read-only
  semantic" live-behavior claims remain in `src/loats` or the pinned
  test docstrings; every surviving 404 mention is historical/dated or
  an unrelated RSS/expiry-hint context.
- `analyzer_intake_semantic` class attribute and its contract pin are
  byte-identical (Amendment 7 data unchanged).
- Zero behavior change: comments and docstrings only; no test
  assertions touched.
