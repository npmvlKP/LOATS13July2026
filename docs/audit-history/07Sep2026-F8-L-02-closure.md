# F8-L-02 Closure Record - as_of_date propagation (CMP Rule 8)

**Date:** 2026-09-07 (Asia/Calcutta)
**Item:** `as_of_date` convention (F8-L-02) - the sole OPEN row of
`docs/audit-history/01Sep2026-FR.md` item 8 as re-derived by
`docs/audit-history/07Sep2026-carried-set-reconciliation.md`.
**Disposition:** CLOSED 2026-09-07.

## What the register demanded

Propagate an explicit, caller-supplied as-of date into decision and
audit records so each record carries the input snapshot date it was
computed from. Acceptance: records carry `as_of_date` equal to the
input snapshot date; the zero-`date.today()` invariant (then
verifier-pinned) must survive; tests must be added rather than spend
the `alerts.py` coverage cushion (82.3 vs floor 80); any touched cycle
test mocks the real producers (PR #6 Linux-CI lesson).

## What was implemented

| Surface | Change |
| --- | --- |
| `src/loats/models.py` | `TradeDecision.as_of_date: date \| None` field (default `None`, never wall-clock derived); `to_analyzer_payload()` emits the ISO string (or `None`). |
| `src/loats/trade_decision.py` | `TradeDecisionEngine.create_trade_decision(..., as_of_date=None)`; single normalized `as_of_iso` echoed in every creation/rejection result payload; decision model stamped; ROUTE audit `metadata.as_of_date`. |
| `src/loats/orchestrator.py` | `_execute_cmp_strategy(as_of_date=None)` parameter, propagated to the engine call site. |
| `src/loats/database.py` | `trade_decisions.as_of_date TEXT` - fresh DDL appends the column LAST (index 22) and the legacy migration is an `ALTER TABLE ADD COLUMN`, so the positional row reader (`_row_to_trade_decision`, length-guarded at index 22) agrees on both schema paths; sync `create_trade_decision` INSERT carries the ISO value; CREATE audit rows carry it via `new_state` (`_model_to_dict` of the model). |
| `src/loats/database_async_additions.py` | aiosqlite `_async_record_trade_decision` INSERT extended identically (23 placeholders). |
| `scripts/verify_carried_set_external.py` | `check_as_of_date_open` -> `check_as_of_date_closed`: enforces implementation presence across the chain (model field, engine + orchestrator parameters, persisted column), keeps the zero-`date.today()` invariant check, and requires this closure state in the reconciliation record. |
| `tests/test_repo_hygiene.py` | `TestCarriedSetExternalVerifier` RED direction rebuilt: the verifier must fail when the persistence leg is stripped from a snapshot whose record claims closure. |
| `scripts/ratchet_baseline.py` | `TRACKED_FILE_CEILING` 393 -> 395 with the F8-L-02 closure wave entry (+2 tracked files: the acceptance net and this record). |

## Behaviour contract

- Caller supplies the snapshot date (e.g. a backtest runner pins
  `2026-09-01`); every produced record - decision model, analyzer
  payload, workflow result payloads, persisted row, CREATE and ROUTE
  audit rows - carries exactly `2026-09-01` (ISO-8601).
- Omitting the date (the live-cycle default) leaves every record
  unpinned (`None`) - observable behaviour of the live path is
  unchanged; nothing in src/loats derives the date from the wall clock.
- Pre-existing `trade_decisions` rows (no as-of column) read back as
  `None` after migration; the SQLite round trip preserves both pinned
  and unpinned rows.

## Acceptance evidence

- `tests/test_as_of_date_propagation.py` - 11 tests, all passing:
  - `TestEnginePropagation` (4): engine stamps the caller date into the
    decision and result payloads; rejection diagnostics carry it;
    omitted input leaves `None` with the uniform key echo; analyzer
    payload carries the ISO value.
  - `TestDatabaseRoundTrip` (2): SQLite round trip preserves the pinned
    value and the absence; column present in the schema.
  - `TestAuditPropagation` (2): CREATE audit row `new_state` and ROUTE
    audit row `metadata` carry the same ISO value.
  - `TestOrchestratorPropagation` (2): end-to-end cycle stamps the
    caller date into the decision, CREATE and ROUTE audit rows; default
    cycle leaves records `None`. Real producers are mocked at the cycle
    boundary (AsyncMock; PR #6 Linux lesson).
  - `TestZeroDateTodayInvariant` (1): zero `date.today()` occurrences
    across `src/loats` enforced in-suite.
- `alerts.py` was not modified (coverage cushion untouched, per the
  register constraint).
- Fresh-schema vs legacy-schema parity is pinned by the index-22
  reader guard tested in `TestDatabaseRoundTrip`.

## Verification state

- Acceptance suite: 11/11 passed on Windows (Python 3.11.16 venv,
  `loatsNEW/Scripts`).
- External verifier: all carried-set dispositions verified from a clean
  process against the working tree.
- Full-suite quality-gate re-run and PR delivery follow this record;
  merge evidence (post-merge pipeline run) to be attached to the PR.

## Ratchet

Two tracked files added (acceptance test + this record):
`TRACKED_FILE_CEILING` 393 -> 395 in `scripts/ratchet_baseline.py`
(single canonical source), wave entry logged in its module docstring.
