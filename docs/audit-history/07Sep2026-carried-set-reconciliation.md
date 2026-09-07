# Carried-Set Reconciliation Record (01Sep2026-FR.md, item 8)

**Date:** 2026-09-07 · **Scope:** register item 8, the carried set from
`docs/audit-history/01Sep2026-FR.md` sections 4, 13, and 18 (F8-L-01
through F8-L-06 plus the named carried items) · **Trigger:** pre-delivery
inspection for the ASCII-gate wave found the register naming
bloombergquint as open while repository evidence shows it closed. The
entire carried set was re-derived against the tree before this record
was written. **Verdict:** seven of eight carried items are CLOSED or
DISCHARGED in code and CI; `as_of_date` (F8-L-02) is the sole open item.

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
| `as_of_date` convention (F8-L-02, CMP Rule 8) | **OPEN** | Zero occurrences of `as_of_date` in `src/` (grep-verified). Decision/audit records do not carry an explicit as-of date, so backtests cannot pin results to an input snapshot date -- a determinism gap that must close before the next `backtest_sanity` change. |

## Registered next step for the open item

`as_of_date` (F8-L-02): propagate an explicit, caller-supplied as-of
date into decision and audit records, so each record carries the input
snapshot date it was computed from. Acceptance per the register: a test
asserts decision/audit records carry `as_of_date` equal to the input
snapshot date; no `date.today()` may be introduced anywhere on the path
(zero-`date.today()` invariant already holds and must survive).
Constraints: `alerts.py` sits at the thinnest coverage margin among the
floor-mapped modules (82.3 vs floor 80), so the implementation wave must
add tests rather than spend that cushion; scheduler/orchestrator seams
touched by the propagation follow the PR #6 Linux-CI lesson (AsyncMock
real producers in cycle tests).

## External verifier

`scripts/verify_carried_set_external.py` re-derives every disposition
above against the live tree (module presence, settings content, marker
constants, artifact fields, ancestry, and the `as_of_date` OPEN state)
and is wired live by
`tests/test_repo_hygiene.py::TestCarriedSetExternalVerifier`. If any
disposition drifts -- a module disappears, a marker is renamed, or
`as_of_date` lands in `src/` without this record being updated -- the
verifier fails CI.
