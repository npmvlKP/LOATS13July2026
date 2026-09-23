# F9-H-05 (TODO-14) — CMP P3 Ensemble / Decay / Bounds: Delivery Record

**Date:** 2026-09-21 · **Scope:** FR9 F9-H-05 remediation — hard
[-1, +1] score bounds, 4 h half-life recency decay, the 70/30 ensemble
scaffold (news leg real, social leg ADR-deferred), and the cold-path
aggregation dedup. Unblocked by F9-H-03 (PR #53) and its BG-1 close-out
(PR #65): the producer persists again, so P3 signal quality is
reachable.

## 1. The defect (re-verified at HEAD before implementation)

FR9 (15Sep2026 report, §2 F9-H-05) recorded, clause-by-clause against
CMP P3 "RSS+VADER ensemble (news 70/social 30), decay. Gate: scores
always [-1,+1]":

- `sentiment_score: float` unbounded on BOTH `NewsItem` (models.py:297)
  and `SentimentAnalysisResult` (models.py:434);
- no decay function anywhere;
- no ensemble weighting anywhere; the plan-level `SOURCE_WEIGHTS` /
  "news 70/social 30" symbol exists in NO code path (repo-wide grep at
  HEAD: only mention is the FR9 report itself; the closest real analog
  is `strength.py` `source_weights` — TA 0.4 / sentiment 0.3 /
  price-action 0.2 / volatility 0.1, a different concern);
- no property test guarding the range.

Live pre-implementation probe (21Sep, this wave):
`SentimentAnalysisResult(sentiment_score=1.5 / -1.5 / 100.0)` all
ACCEPTED and stored verbatim; `loats.sentiment` had neither
`ENSEMBLE_WEIGHTS` nor `SENTIMENT_HALF_LIFE_HOURS`.

Root cause: P3 shipped as a plain VADER mean; ensemble/decay/bounds
were never implemented and never re-flagged until FR9's clause-by-clause
pass.

## 2. Fix (ADR-0017, all three spec parts + hygiene)

1. **Bounds as a HARD model invariant** (models.py):
   `sentiment_score: float = Field(ge=-1.0, le=1.0)` on both models.
   The gate sits at the model boundary — every future producer and
   every deserialized payload crosses it; VADER compound scores are in
   range by construction, so rejection fires only on corrupt/foreign
   input. Blast-radius grep before the change: all 20
   `sentiment_score=` test constructions in range; zero production
   constructions out of range possible (VADER bound).
2. **Recency decay** (sentiment.py `_compute_and_count`):
   `0.5 ** (age_hours / 4)` per article, applied BEFORE averaging;
   timezone-aware UTC math; non-positive ages (future-dated items —
   clock skew, wrong feed tz) clamp to the fresh weight 1.0 so skewed
   feeds cannot earn above-full weight; final `max(-1, min(1, ...))`
   clamp enforces the P3 gate at the aggregation boundary too.
   Documented semantic (ADR-0017 Consequences): a NORMALIZED weighted
   mean expresses RELATIVE recency — mixed-age sets reweight toward
   the fresh side; a uniformly-aged set scores its plain mean (scale
   invariance); whole-set staleness is surfaced by the result timestamp
   and the F9-H-03 degraded chain, not the score.
3. **Ensemble scaffold**: `ENSEMBLE_WEIGHTS = {"news": 1.0}` — the
   news leg at full weight on the CMP 70% scale. The social leg (CMP's
   30%) is ADR-DEFERRED: no social producer exists and FR9 forbids
   fabricating one. Adding it later is a one-key extension; the
   weighted aggregation normalizes automatically.
4. **Aggregation dedup (found during the wave)**: the F9-H-03 wave
   left the cold-start path and `_compute_and_count` with duplicated
   aggregation logic (~50 drift-prone lines). The cold path now
   delegates to the shared core (spy-pinned:
   `TestColdPathDelegation`); the refresh path's unreachable
   `if fresh is not None` dead branch (unreachable by type contract,
   masked by a bare `except`) is removed; the legacy per-feed failure
   tolerance (`gather(..., return_exceptions=True)` — one dead feed
   degrades, never raises) is preserved and pinned
   (`TestLegacyFailureTolerancePreserved`).
5. **Legacy pin corrected with citation** (BG-1 precedent):
   `tests/test_sentiment.py` fed a naive `datetime.now()` into the
   aggregation — under timezone-aware decay math that is a TypeError.
   Corrected to `datetime.now(UTC)` with the in-line citation. Audit:
   the only naive-`published_date` construction flowing through
   aggregation in the suite (test_models' 2023-dated items are
   construction-only).

## 3. Mid-wave corrections (RECHECK honesty — both were pin defects,
neither a production defect)

1. The original "0.8 at exactly 4 h scores 0.4" expectation was
   mathematically wrong for a normalized weighted mean: a single
   article's score equals its own weighted average at ANY age
   ((0.8·0.5)/0.5 = 0.8 — scale invariance). Replaced with the
   invariance pin, symmetric age-dominance hand-computed pins
   (+0.2 / −0.2), and strict monotonicity against a fixed fresh
   anchor. The passing mixed-set pin (0.44) had already proven decay
   works; the failed pin proved the semantic needed documenting.
2. The seeded-fuzz and monotonicity loops reused symbol keys, so
   iterations 2+ served iteration 1's BY-DESIGN 5-minute result-cache
   entry (5 ≠ 6 news_count exposed it). Unique symbol per iteration;
   the cache behaving correctly is itself contract evidence.

## 4. TDD evidence

- RED-first: `tests/test_sentiment_p3_ensemble_f9h05.py` failed at
  collection (`ImportError: cannot import name 'ENSEMBLE_WEIGHTS'`)
  before the implementation; the bounds pins had live-probe evidence
  (§1).
- GREEN: 29/29 pins pass; full affected surface — test_sentiment,
  test_sentiment_coverage, test_sentiment_f9h03_producer,
  test_sentiment_ttl_horizons_f9h03, test_models, test_orchestrator,
  test_orchestrator_extra, test_scheduler, test_cache,
  test_cache_additional, test_cache_concurrency,
  test_repo_hygiene, test_single_engine_consolidation —
  **348 passed / 0 failed** (21Sep run).
- Erratum (23Sep2026): this list originally named `test_strength` among
  the surface modules, but `tests/test_strength.py` was deleted on
  2026-07-21 (`bcc09c1`) — two months before this record's date — and is
  absent at both of this wave's commits (`bd0b07f`, `633daae`); the 21Sep
  "348 passed" run therefore cannot have included that literal file (the
  module list was transcribed imprecisely). The list above is corrected
  to the 13 surviving modules; the run tally itself is corroborated — the
  corrected 13-module surface plus the pin module re-ran clean at HEAD
  `7e124c3`: **394 passed / 0 failed** (158.6 s). `src/loats/strength.py`
  itself remains live and unaffected by this correction.
- Counts are decay-invariant (tallies pinned), bounds fuzz is seeded
  (`random.Random(0xF9E05/6)` — deterministic, no hypothesis
  dependency; ADR-0010 dependency-austerity precedent).

## 5. Adversarial round 2 (independent review — CONDITIONAL_PASS, all
## findings dispositioned)

A fresh static-only reviewer subagent graded the wave against the FR9
spec and this ADR (21Sep). Six findings; the round verified the
reviewer's arithmetic by probe before fixing (underflow threshold
reproduced at 4290→4300 h; 0.0/0.0 raise reproduced; corrected hand
values confirmed 0.0000/-0.0691/-0.2667/-0.4800/-0.7754/-0.8000):

1. **ENSEMBLE_WEIGHTS declared but not consumed (AR-1/AR-3)** — valid:
   the "falls out of the weights" phrasing in the ADR and module
   comment overclaimed one-key activation. Corrected to the honest
   contract (DECLARATIVE machine-readable scaffold; wiring 70/30
   requires an ADR amendment PLUS leg tagging PLUS aggregation
   changes), enforced by pins (`TestAdversarialRound2`:
   aggregation source must not reference the constant; signature
   frozen; type contract).
2. **All-ancient underflow ZeroDivisionError (AR-2)** — REAL defect,
   fixed: `0.5**(age/4)` underflows to exactly 0.0 at ≳4300 h; an
   all-ancient set hit 0.0/0.0 and would have crashed the cold path
   where the deleted inline code returned the plain mean. Fallback to
   the clamped plain mean restores the legacy degradation; 3 pins.
3. **Log-observability drift (dedup)** — restored: feed-failure
   logging back to ERROR level in the shared core.
4. **Monotonicity docstring hand values wrong for 4 of 6 ages** —
   corrected to the probe-verified values.
5. **Bounds pins never exercised deserialize/round-trip/nested paths**
   — 7 pins added (cached JSON payload rejects out-of-range, in-range
   round-trip preserves score+degraded, nested `top_news` rejects
   out-of-range items).
6. **RED-first evidence is collection-level; surface run
   unverifiable statically** — accepted as an evidence-granularity
   observation: the RED state is the collection ImportError (same
   signature as the F9-H-03 wave), the bounds defect had the live
   pre-implementation probe (§1), and the surface/full-tree runs carry
   their log stamps in `reports/`.

## 6. Pre-push-gate catch (round 3): fresh-age float flake

The first push attempt was REJECTED by the gate's own full-tree run:
`test_analyze_symbol_sentiment_positive_overall` flaked
(`0.8999999999999999 != 0.9`) — both local full-tree runs had passed
by timing. Root cause (reproduced, not inferred): a just-parsed
article is 1-10 ms old; its decay weight 0.5**(age/4) lands at
1 - ~5e-11 — NOT exactly 1.0 — adding one float rounding to the
weighted mean, so strict-equality legacy pins flake depending on the
construction→aggregation microsecond delta (the failing run sampled a
10 ms async-scheduling gap). Fix: ages ≤ `FRESH_AGE_SNAP_HOURS`
(100 ms — below any real feed timestamp granularity) snap to the
exact fresh weight 1.0; the weighted path below the snap is
bit-identical to the legacy plain mean, and the boundary
discontinuity is ~5e-9 of relative weight. 4 pins added
(`TestFreshAgeSnap`, including the exact `==` reproductions for
±scores); legacy pins untouched (no assertion loosening anywhere).

## 7. Ceiling

`scripts/ratchet_baseline.py` 450 → 453: +3 tracked files (this
record, the pin module, ADR-0017), re-pinned per the documented
single-source protocol with a dated changelog entry.
