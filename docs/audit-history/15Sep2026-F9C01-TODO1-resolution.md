# F9-C-01 / TODO-1 Resolution Record — iv_rank correctness + fail-closed history

**Date:** 2026-09-15 · **Finding:** FR9 F9-C-01 (Critical, P0 — execute FIRST) with F9-M-04 merged
**Branch:** `main` @ `57b77a0` (base) · **Protocol:** STRICT LOATSEV (BUILD → ... → CONFIRMED & VERIFIED)
**CMP basis:** Section 4 gating rules — BUY at `IV rank < 30`, SELL at `IV rank > 40`.

## Root cause (verified, not assumed)

`CMPRulesEngine.calculate_iv_rank` divided an **annualized** stdev
(`np.std(returns) * sqrt(252)`, magnitude ~0.1-0.25) by the **daily**
min/max return spread (~0.02-0.05), then `np.clip(x*100, 0, 100)` — a
deterministic saturation to 100.0 for every sufficient-history input.
The `len(historical_data) < window -> return 0.5` silent fallback let
the BUY gate (`0.5 < 30`) pass on no data.

Reproduced on base HEAD before the fix (this session, real interpreter):

- Synthetic probe: 5 daily-vol regimes (0.2%-4%) x 3 seeds -> **15/15 = 100.0**.
- Live gating at `len == window` boundary: `iv_rank = 100.0` rejected the
  BUY leg end-to-end (F9-C-01 evidence item 4 confirmed mechanically).

## Correction (root-cause, not symptom)

1. **Units-consistent rank (fallback source):** percentile rank of the
   CURRENT bar's absolute return within the window's absolute returns
   (daily vs daily). Zero-spread window -> 0.0 (honest min), never 0.5.
2. **True IV rank (preferred source):** option-chain ATM IV series via
   `set_chain_iv_history` (bounded 252-day deque); rank =
   `(current - min) / (max - min) * 100` over the series. Fed once per
   cycle by the options-flow producer from the real broker chain
   (`_extract_atm_iv`, minimum-|strike-spot| within 1%, fraction/percent
   units normalized at ingestion).
3. **Persistence (`iv_history` table):** keyed `symbol + as_of_date`
   (one upserted row per trading day; 252-day read window = 1 trading
   year). `as_of_date` comes from the caller or, wall-clock-free, from
   the furthest parseable expiry in the chain payload (zero
   wall-clock-date invariant preserved; no parseable expiry -> honest
   in-memory-only degradation).
4. **Warm-start:** orchestrator `initialize()` loads the persisted
   series so the first post-restart cycle has full history depth.
5. **Loud insufficiency (F9-M-04):** `< window` bars AND no IV series
   -> `float("-inf")`; gating fails BOTH directions closed with
   `reason="insufficient_history"` + fail-closed per-gate flags, and the
   rejection is audit-logged by the existing `_audit_rejection` path.
6. **Provenance:** every gating outcome carries `iv_source` in
   {"iv_series", "hv_percentile"} so the rank's origin is auditable.

CMP threshold lines `iv_pass = iv_rank < 30` (BUY) and
`iv_pass = iv_rank > 40` (SELL) are preserved verbatim inside
`apply_gating_rules` — the HC-24 source-pinned verifiers in
`scripts/fr7_health_check.py` and `scripts/verify_hc_registry.py`
remain green by construction.

## Verification evidence (live, this session)

- New regression suite `tests/test_iv_rank_f9c01.py`: **19/19 PASS**
  (RED-first proven on base: 15 tests failed for the documented legacy
  reasons — degenerate `[100.0 x 15]`, silent 0.5, unreachable BUY).
- Before/after probes: saturation **15/15 -> 0/15**; BUY leg reachable
  (rank 0.0, ADX 60.4, VIX 10) and SELL leg reachable (rank 65.7,
  ADX 5.2, VIX 20) on real gating paths.
- Boundary hand-computation: rank 50.0 -> SELL pass; rank 0.0 -> BUY
  pass at the pinned 30/40 lines.
- `tests/test_rules_engine.py` legacy pin (`== 0.5`) updated to the
  corrected loud contract with FR citation.
- Quality gates re-run after the change: ruff check+format PASS;
  isort/flake8 PASS; mypy `src/ --strict` PASS (38 files); bandit `src/`
  0 findings (B105 false positive avoided via locals, no nosec);
  pip-audit 0 vulnerabilities; gitleaks 586 commits no leaks; HC-24
  pinned-source check PASS.
- Full suite + coverage: see session summary (1858 collected;
  coverage floor 80 enforced).
