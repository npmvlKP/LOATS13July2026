# F9-M-05 (TODO-15) — CMP §4 Strike Conformance: Root Cause & Resolution

**Finding:** FR9 §3 F9-M-05 — "Strike selection off-spec: no true
0.50–0.60 delta band; SELL-side 2SD absent." Severity Medium, confidence
Certain, remediation TODO-15.

**Status:** RESOLVED 2026-09-18 (this wave). The production cycle path is
unaffected in behavior for `atm_straddle` (the strategy the orchestrator
invokes); the conformant band, 2σ band builder, and OI confirmation now
exist as first-class, pinned surfaces of the strike engine.

## Root cause (verified)

`_select_delta_neutral_strikes` implemented the CMP "delta 0.50-0.60 buy"
clause as an open "prefer close to 0.5" heuristic
(`abs(opt.delta - 0.5) < 0.1` / `abs(opt.delta + 0.5) < 0.1`):

- the band was OPEN (0.40, 0.60) — delta 0.41 passed, and delta 0.60
  exactly was REJECTED (strict `<`);
- the sell side had NO implementation at all (grep for 2SD/2σ logic was
  empty across the repo — FR9 evidence confirmed);
- the OI check existed only as a separate `oi_based` strategy, never as
  the confirmation filter CMP §4 requires;
- latent defect found during the wave: the ATM call and put strikes were
  appended unconditionally and un-deduplicated, so the standard ATM pair
  (100CE + 100PE) produced the selection `[100.0, 100.0]` — the legacy
  test actually pinned this duplicate (`len(selected) == 2` on a
  same-strike pair).

## Remediation (TODO-15 spec, complete)

1. **BUY-side closed band**: module constant pair
   `DELTA_BAND_LOW=0.50` / `DELTA_BAND_HIGH=0.60` with
   `delta_in_buy_band()` — closed on both ends, applied to |delta| so
   put magnitudes qualify symmetrically, `None` delta fails closed.
2. **SELL-side 2σ band**: `estimate_bar_sigma()` computes the sample
   stdev of simple per-bar returns over a SINGLE-interval series;
   `two_sigma_sell_band()` scales it to the holding horizon with
   `TRADING_DAY_SECONDS = 22500` (root source:
   `TradingRulesEngine.get_current_session()` REGULAR session 09:15–15:30
   IST) — `sqrt(days * 22500 / bar_seconds)`, so per-bar and 252-day
   annualized sigma conventions agree (252·22500/22500 = 252 bars).
   Interval labels parse strictly as `<n>min` (the codebase's only
   produced form, `settings.default_timeframe = "1min"`); anything else
   is unit-ambiguous and fails closed rather than guessing.
3. **OI confirmation filter**: band-eligible contracts additionally
   require `open_interest >= MIN_OI_CONFIRMATION (1)` — zero/negative OI
   fails closed; missing delta fails closed.
4. **Dedup root-cause fix**: selections are deduplicated; the ATM
   call+put pair at one strike yields that strike once.
5. **Engine surface**: `build_sell_two_sigma_band()` end-to-end builder
   (history in, band out, `None` on any fail-closed path).

## TDD evidence

- RED-first: `tests/test_strike_selection_f9m05.py` — 22 failed /
  3 passed (the 3 passes being cases the old code satisfied for the
  wrong reason: constants not yet pinned, symmetric-argument and
  band-symmetry helpers absent).
- GREEN: 28/28 new pins, including the FR9-specified boundaries
  0.49/0.50/0.60/0.61, hand-computed σ (returns +0.01/−0.01 ⇒
  σ = 0.01·√2) and hand-computed 2σ band (σ=0.02/bar, 16 bars/day,
  4 days ⇒ band [68.0, 132.0] on a 100.0 underlying), OI-missing
  fail-closed, mixed-interval and unparseable-interval fail-closed,
  insufficient-history fail-closed, max_strikes cap, empty chain, and
  the dedup root-cause pins.
- Legacy net updated where its assertions encoded the OLD off-spec
  behavior (2 assertions): `test_select_strikes_delta_neutral` (out-of-band
  0.65/0.35 legs must now be excluded; ATM pair dedups to one strike) and
  `test_delta_neutral_edge_cases` (same dedup pin). All other 16 legacy
  tests pass unmodified.
- Gates: ruff check clean, ruff format clean, isort clean, flake8 clean,
  mypy strict clean (strike_selection.py), bandit clean; module coverage
  97% branch-aware against the 75% F8-H-04 floor (pre-wave 87.0%);
  every line of new F9-M-05 code is covered.

## P5 span-safety statement

The live supervisor runs pre-wave code until its restart; nothing in
this wave touches a running process. The orchestrator's cycle path
(`_execute_strike_selection`) invokes `atm_straddle` and is unchanged;
the conformant delta-band/2σ surfaces are additive engine APIs with no
new runtime dependencies (stdlib `math`/`re`/`statistics` only). No CMP
decision semantics, breaker, grader, or audit surface is modified. The
two updated legacy assertions are test-only files; no production caller
of `_select_delta_neutral_strikes` exists outside the engine itself
(single call site: `select_strikes` dispatch).
