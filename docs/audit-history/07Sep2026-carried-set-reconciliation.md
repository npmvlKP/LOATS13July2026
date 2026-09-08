# Carried-Set Reconciliation Record (01Sep2026-FR.md, item 8)

**Date:** 2026-09-07 · **Scope:** register item 8, the carried set from
`docs/audit-history/01Sep2026-FR.md` sections 4, 13, and 18 (F8-L-01
through F8-L-06 plus the named carried items) · **Trigger:** pre-delivery
inspection for the ASCII-gate wave found the register naming
bloombergquint as open while repository evidence shows it closed. The
entire carried set was re-derived against the tree before this record
was written. **Verdict:** seven of eight carried items were CLOSED or
DISCHARGED in code and CI at PR #7; the last open item, `as_of_date`
(F8-L-02), was CLOSED 2026-09-07 by the F8-L-02 closure wave (see the
per-item table below). The carried set now stands at eight of eight.

The register document itself is a frozen 01Sep audit artifact and is not
edited retroactively; per house convention this outcome record carries
the corrected state, and the CI-pinned verifiers are the enforcement
layer.

## Per-item dispositions (evidence at PR #7 tree, run 34137424644)

| Item | Disposition | Evidence |
| --- | --- | --- |
| vollib migration (ADR-0004, TODO-27a) | CLOSED | `src/loats/options_math.py` hand-rolled Black-Scholes ("Replaces the deprecated `vollib` dependency"), byte-compatible scaling pinned by `tests/test_options.py` / `test_options_coverage.py`; vollib absent from runtime dependencies. |
| Per-source breakers (F8-L-01, CMP P5) | CLOSED | `src/loats/utils/per_source_breakers.py` registry keyed by `StrengthSource`, imported by `orchestrator.py`; isolation semantics pinned by `tests/test_per_source_breakers.py`. |
| bloombergquint feed (F8-L-05) | CLOSED | Feed removed from `settings.rss_feeds` by TODO-27d (description: "Validated RSS feeds (bloombergquint removed)"); `src/loats/rss_validation.py` is the proof layer -- recorded-fallback manifest validated offline at startup, live re-validation degrades to WARNING, and `DEFUNCT_FEED_MARKER` rejects any bloombergquint reappearance outright; guarded by `tests/test_rss_validation.py`, the CI `rss-feeds` job (green on this run), and `scripts/verify_todo27_eval.py` F1/F2. The register's own S04 row already records this closure; the F8-L-05 section-4/13 lines are stale narrative. |
| Broker idempotency honoring | CLOSED at client boundary | `src/loats/openalgo.py` sends an `Idempotency-Key` header on every order operation (place/modify/cancel; UUID v4 get-or-create with TTL cache); module note records that OpenAlgo server-side honoring is unconfirmed; `database.py::store_order` enforces `idempotency_key` dedupe. Residual broker-side confirmation is an integration-testing item, not a code gap. |
| Live P1 re-measurement (F8-L-03) | DISCHARGED 2026-09-04 | Tracked artifact `reports/p1_analyze_latency_20260904_040609.json` (`measurement_scope: live-endpoint`, `p1_discharging: true`, fix version 3.0): 100/100 successful live TCS round trips to the configured OpenAlgo endpoint, mean 57.62 ms, P95 74.05 ms, 100% live-gate compliance, pinned by HC-29 and `verify_todo25_*`. The register's client-side-only caveat is superseded by the two-scope artifact. |
| Direct-push probe debris (F8-L-04) | DISCHARGED | `44f91515` and `0576eb36` are absent from `main` ancestry (merge-base verified; objects GC'd). Branch protection verified server-side via the API (PR + required checks + approval, admins enforced) and re-proven operationally by every wave since (PR #6, PR #7). |
| nltk warning (F8-L-06) | CLOSED | Suppression knob `LOATS_SUPPRESS_NLTK_WARNING` shipped; dev-toolchain triage recorded in ADR-0010 with the pip-audit waiver. |
| `as_of_date` convention (F8-L-02, CMP Rule 8) | CLOSED 2026-09-07 | Implemented by the F8-L-02 closure wave: caller-supplied `as_of_date` (optional `datetime.date`, default `None`) propagates through `TradeDecisionEngine.create_trade_decision` and `TradingOrchestrator._execute_cmp_strategy` into the created `TradeDecision` (model field on `src/loats/models.py`), its `to_analyzer_payload`, every rejection/creation result payload, the persisted `trade_decisions.as_of_date` column (fresh DDL + legacy `ALTER TABLE ADD COLUMN` migration, appended LAST so the positional row reader sees index 22 on both schema paths), CREATE audit rows (`new_state` via `_model_to_dict`), and ROUTE audit rows (`metadata`). Acceptance pinned by `tests/test_as_of_date_propagation.py` (11 tests): records carry `as_of_date` equal to the input snapshot date; omitted input leaves records `None` so live-cycle behaviour is unchanged; the zero-`date.today()` invariant is enforced in-suite and by the external verifier. No `alerts.py` code touched; producers in the touched cycle test are AsyncMock-mocked (PR #6 Linux lesson). |

## Disposition of the registered next step

The registered next step above was executed as the F8-L-02 closure wave
(2026-09-07). The carried set now stands at eight of eight items
CLOSED or DISCHARGED; no open item remains on this register.

## External verifier

`scripts/verify_carried_set_external.py` re-derives every disposition
above against the live tree (module presence, settings content, marker
constants, artifact fields, ancestry, and the `as_of_date` CLOSED state
-- acceptance anchors across the propagation chain plus the zero
`date.today()` invariant) and is wired live by
`tests/test_repo_hygiene.py::TestCarriedSetExternalVerifier`. If any
disposition drifts -- a module disappears, a marker is renamed, or the
`as_of_date` implementation chain is removed without this record being
updated -- the verifier fails CI.
