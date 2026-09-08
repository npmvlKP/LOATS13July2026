# F8-C-01 Wave 2 - Options-Flow Producer (5th Source)

**Date:** 2026-09-08 (Asia/Calcutta)
**Wave:** closes the F8-C-01 residual the 4/7 closure left open:
producer coverage 4/7 passed the diversity gate but had zero outage
redundancy - one per-source breaker trip dropped a live cycle to 3/7
= 0.429 < 0.5 and the CMP chain went dark again.

## Root cause addressed

Not a missing source per se - the 4/7 set satisfies gate math - but the
structural fragility that 4/7 encodes: with the minimum passing set and
no spare, any single producer outage (breaker trip, provider hiccup)
silently voids every decision. The 08Sep risk register carried this as
"producer coverage 4/7 (F8-C-01); highest-priority code work".

The fix is a genuine 5th source, not diversity theater:

- `OPTIONS_FLOW` has a real feed: `AsyncOpenAlgoClient.get_option_chain`
  (broker option-chain endpoint, 5-minute response cache) existed with
  zero production callers, and the options analytics stack
  (`options_math.py`, `strike_selection.py`) was already in-tree.
- `FUNDAMENTAL` was evaluated and rejected: broker `get_funds` returns
  account cash/margin, not company fundamentals - tagging that feed as
  a fundamental producer would fabricate diversity from one data
  source (the exact anti-pattern F8-C-01 was raised to eliminate).
- `MACHINE_LEARNING` rejected: no model-serving infrastructure exists
  in the repository.

## What was implemented

| Surface | Change |
| --- | --- |
| `src/loats/orchestrator.py` | `_execute_options_flow_analysis` (5th producer: put/call volume flow + IV skew from the nearest-expiry chain, persisted via `db.async_create_signal`; PCR >= 1.2 SELL / <= 1/1.2 BUY / dead-band NEUTRAL 0.5, conviction capped +0.3; IV skew recorded, not gating - index put skew is structurally positive). Fetch path `_source_guarded_option_chain` -> `_safe_get_option_chain` -> `_fetch_option_chain_bare` (per-source breaker + global breaker+retry + innermost seam, mirroring history/quotes). Schema-tolerant extraction helpers (`_extract_chain_rows`, `_nearest_expiry_rows`, `_chain_int`, `_chain_float`) degrade to no-signal on empty/malformed/illiquid payloads - never a fabricated Signal. Producer joined to the cycle gather inside the `producer_window_seconds` boundary. |
| `src/loats/utils/per_source_breakers.py` | `ACTIVE_SOURCES` gains `OPTIONS_FLOW` per the registry's documented landing rule (breaker fleet = live producer set; `FUNDAMENTAL`/`MACHINE_LEARNING` remain fail-closed). |
| `scripts/verify_f8c01_external.py` | `REQUIRED_SOURCES` = 5; check_1 expects 5 emission sites; check_4 drives the real five producers (chain fixture patched at `_safe_get_option_chain`) and proves the stored set passes `validate_signal_sources`; docstring updated (5/7 = 0.714). |
| `scripts/probe_hc15_strength_gate.py` | Required production set includes `OPTIONS_FLOW`; gate-math probe now asserts 3-src rejected / 5-src accepted; amendment note records the redundancy rationale. |
| `scripts/fr7_health_check.py` | HC-15 required emission set includes `OPTIONS_FLOW`. |
| `tests/test_e2e_cmp_chain.py` | `make_chain_payload` fixture (OpenAlgo envelope, CE/PE spellings); 5-producer driver asserts all 5 tagged sources stored; `TestMutationSafety` pins the 5th producer method. |
| `tests/test_single_engine_consolidation.py` | `_chain_payload` fixture; both real-producer drivers run and count the 5th source. |
| `tests/test_orchestrator.py`, `tests/test_orchestrator_extra.py`, `scripts/verify_f8m02_m07_external.py` | Cycle-gather mock walls include `_execute_options_flow_analysis` so the F8-M-02 settle tests spy on the full producer set. |
| `tests/test_per_source_breakers.py` | Fleet/status pins = 5 sources; `OPTIONS_FLOW` moved out of the dormant set. |
| `tests/test_signal_source_invariant.py` | `resolve_source` acceptance set includes `options_flow`. |
| `docs/ADR-005-price-action-producer.md` | Amendment section: 5th producer rationale, signal model, breaker-fleet landing, dormant-member disposition. |
| Hygiene (same wave) | `reports/verify_f8h01_external.json` untracked and its verifier redirected to the ignored `reports/health/p5-verify-stubs/` path - per-run mutable output leaves the tracked evidence stream (the recorded H-01-churn wart); allowlist/consumer pins updated in `check_repo_hygiene.py`, `verify_f8m02_m07_external.py`, `tests/test_repo_hygiene.py`. `scripts/ratchet_baseline.py` changelog deduplicated (F8-H-02 wave was recorded twice). |

## Verification state

- Targeted suites green: per-source breakers, orchestrator (+extra),
  e2e CMP chain, single-engine consolidation, signal-source invariant,
  repo hygiene (F8-M-02/M-03 nets), trade decision.
- External verifiers green: `verify_f8c01_external.py` (7 checks),
  `probe_hc15_strength_gate.py`, `verify_f8m02_m07_external.py`,
  `verify_f8h01_external.py` (writes only the ignored path now),
  `verify_carried_set_external.py` (5 active breakers, distinct).
- Gates green: ruff check + ruff format, isort, flake8 (src strict),
  mypy src/ --strict, bandit.
- Full suite with CI-exact coverage flags: see the dated gate run in
  this wave's commit message.

## Behaviour contract

- Live cycles now launch six producer tasks; the options-flow producer
  costs one broker call per 5-minute TTL window (client-side cache) and
  emits at most one signal per cycle.
- Diversity: 5/7 = 0.714 nominal; any single producer outage -> 4/7
  = 0.571, still passing. Two simultaneous outages (3/7 = 0.429) fail
  the gate loudly via the existing `insufficient_source_diversity`
  rejection - unchanged observable behaviour for that path.
- No gate thresholds, weights, or decision logic changed; the only
  decision-path difference is one additional source in the composite
  when the producer has data.

## Risk register delta

- RESOLVED: producer coverage 4/7 (F8-C-01 residual) - production is
  now 5/7 with single-outage redundancy.
- RESOLVED: H-01 verifier tracked-JSON self-churn - output moved to the
  ignored stub path; the dated audit records are the evidence of record.
- NEXT: P5 grading ~21Sep (p5_forward_test_20260907_124455.json,
  resumed run) - Zerodha token re-login + market-hours window required
  before then so counters show MEASURED routing activity.
- NEXT: broker-side idempotency probe; eval re-run recommended before
  wave 4.
