# ADR 0017: CMP P3 Sentiment Ensemble, Recency Decay, and Hard Score Bounds

## Status

Accepted — 2026-09-21

## Context

CMP P3 specifies the sentiment leg as an "RSS+VADER ensemble
(news 70/social 30), decay. Gate: scores always [-1,+1]". FR9's
clause-by-clause pass (F9-H-05, → TODO-14, Certain) recorded that none
of the three clauses shipped: the producer computes a plain VADER mean,
`sentiment_score: float` is unbounded on BOTH `NewsItem` and
`SentimentAnalysisResult` (models.py), no decay function exists, and no
property test guards the range. The remediation was blocked on the
producer persisting at all — resolved by F9-H-03 (PR #53, producer
LKG/degraded chain) and its BG-1 close-out (PR #65, per-entry TTL).
FR9 also recorded (F9-H-05 evidence) that the plan-level
`SOURCE_WEIGHTS` / "news 70/social 30" symbol exists in no code path —
the ensemble scaffold must therefore be created, not repaired.

## Decision

1. **Bounds are a hard model invariant.**
   `sentiment_score: float = Field(ge=-1.0, le=1.0)` on BOTH
   `NewsItem` and `SentimentAnalysisResult`. The gate sits at the model
   boundary (defense in depth), not only inside the producer, so any
   future scoring backend or deserialized payload violates loudly
   instead of silently. VADER's compound score is in [-1, 1] by
   construction and the aggregation clamps, so no in-repo producer can
   trip the invariant; rejection fires only on corrupt/foreign input,
   which is the intent.

2. **Recency decay: 0.5 ** (age_hours / 4), applied per article
   BEFORE averaging.** Timezone-aware UTC arithmetic
   (`published_date` is aware; a legacy naive value would TypeError, so
   `tests/test_sentiment.py`'s one naive `datetime.now()` construction
   is corrected to `datetime.now(UTC)` with an in-line citation — same
   precedent as the BG-1 legacy-pin corrections that pinned defective
   semantics). Non-positive ages (future-dated items: clock skew, wrong
   feed tz) are treated as fresh (weight 1.0) so skewed feeds cannot
   earn >1.0 weight. Decay is a signal-quality weight, not a risk
   control: failing open to fresh is deliberate.

3. **Ensemble scaffold is explicitly news-only and DECLARATIVE.**
   `ENSEMBLE_WEIGHTS = {"news": 1.0}` — the news leg expressed at full
   weight on the CMP 70% scale, as a machine-readable contract
   (imported and shape-pinned). It is NOT an aggregation input: the
   system produces exactly one leg today, so per-article weights are
   the recency factor alone. The social leg (CMP's 30%) is DEFERRED
   because the system has no social-media signal producer and FR9
   explicitly forbids fabricating one. Wiring real 70/30 math when a
   social producer exists requires an ADR amendment PLUS per-item leg
   tagging PLUS weighted-leg aggregation — a code change, stated here
   so no one expects one-key activation (adversarial round 2 corrected
   the earlier "falls out of the weights themselves" overclaim).

4. **One aggregation core.** The F9-H-03 wave left the cold-start
   path and `_compute_and_count` with duplicated aggregation logic.
   The ensemble semantics ship in `_compute_and_count` only; the cold
   path delegates to it (spy-pinned,
   `tests/test_sentiment_p3_ensemble_f9h05.py::
   TestColdPathDelegation`). The legacy per-feed failure tolerance
   (gather with return_exceptions=True; dead feeds degrade, never
   raise) is preserved and pinned.

## Consequences

- Aggregation is a normalized recency-weighted mean: mixed-age sets
  reweight toward the fresh side (newer news dominates, per spec);
  a uniformly-aged set scores its plain mean (scale invariance), so
  whole-set staleness is surfaced by the result timestamp and the
  F9-H-03 degraded chain rather than the score itself. Tallies
  (news/positive/negative/neutral counts) are decay-invariant and
  stay untouched.
- Out-of-range serialized payloads now fail deserialization. No such
  payloads are produced in-repo (VADER is bounded; the ensemble mean of
  clamped values is clamped), so the stricter boundary is safe.
- `scripts/ratchet_baseline.py` ceiling 450 → 453 for the three added
  tracked files (pin module, this ADR, the wave record), re-pinned in
  the same wave per the documented single-source protocol.

## Alternatives Considered

- **Fabricate a social score** to complete the 70/30 arithmetic —
  rejected: FR9 disposition forbids inventing signal sources; a
  fabricated leg would poison the diversity gate's meaning.
- **Apply decay to the pre-average mean** (decay the aggregate, not
  the articles) — rejected: CMP's semantics weight each article by
  recency; decaying the mean cannot express "old article counts
  less".
- **Bounds only at the producer** — rejected: the model boundary is
  the last line of defense and the one place every future producer
  cannot bypass.
