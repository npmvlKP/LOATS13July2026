# F9-H-03 (TODO-4) — Sentiment Producer Death: Root Cause & Resolution

> **2026-09-20 correction (BG-1 close-out):** two claims below were false
> under the then-real cache semantics and are superseded by
> `20Sep2026-F9H03-verification-and-BG1-closeout.md`: (a) "LKG TTL
> 900 s" — `CacheManager.set` ignored its per-call `ttl`, so the entry
> actually expired with the cache-wide 300 s; (b) `degraded=True` was
> unreachable dead code for the same reason (plus threshold ==
> retention). Both are fixed in the BG-1 close-out (per-TTL tier stores;
> threshold 600 s strictly inside the 900 s retention horizon).

**Finding:** FR9 §2 F9-H-03 — "Sentiment producer effectively DEAD: last
signal 13Sep 01:59 UTC; 8–10 s analysis vs 8.0 s window." Severity High,
confidence Certain, remediation TODO-4.

**Status:** RESOLVED 2026-09-17 (this wave). Live supervisor unaffected —
it runs the pre-wave code until the post-30Sep restart; the remediation
activates with that restart.

## Root cause (verified, not inferred)

The orchestrator runs all five signal producers inside one
`asyncio.wait_for(asyncio.gather(...), timeout=settings.producer_window_seconds)`
(8.0 s default). Sentiment's cold path — per-article newspaper4k downloads
executed inline for every entry of every feed — costs 8–10 s, so every cycle
timed out. Cancellation landed **before** `analyze_symbol_sentiment` reached
its 5-minute result cache-set and before `async_create_signal`: the producer
never persisted anything, and the next cycle started equally cold. The
existing result cache was unreachable dead weight under the loop's own
cancellation semantics — a self-sustaining death loop.

Live confirmation (17Sep): 2,133 `Sentiment analysis exceeded budget:
~8000 ms` warnings in the active log, zero producer lines, zero sentiment
signals since 13Sep, cycle times pinned at the window boundary
(7.99–8.87 s). FR9's evidence (DB per-day signal counts 09Sep 29 →
14/15Sep 0) matches exactly.

## Remediation (TODO-4 spec, all four parts)

1. **Article-content cache** (`src/loats/sentiment.py`): per-URL TTLCache
   (5 min, thread-safe — extraction runs on `asyncio.to_thread` workers).
   Completed downloads survive producer cancellation, so each cycle
   re-downloads strictly less and cold analysis converges inside the window.
2. **Last-known-good (LKG) serving + detached refresh**: on result-cache
   miss, the stored LKG result is served immediately; a **detached** task
   re-runs the aggregation and overwrites the result + LKG entries. The
   task is cache-only (never touches signals/DB), so the F8-M-02 invariant
   "no signal outlives the producer window" is structurally preserved.
   LKG TTL 900 s (`LKG_TTL_SECONDS`).
3. **Degraded tagging**: an LKG result older than its TTL still serves (a
   signal beats no signal for the diversity gate) with
   `SentimentAnalysisResult.degraded=True`; the orchestrator stores
   `degraded` in the signal metadata (audit-visible provenance).
4. **Per-source liveness alert**: `_check_sentiment_liveness` in the cycle
   (after risk management, before CMP) — during REGULAR session, a latest
   sentiment signal older than
   `SENTIMENT_LIVENESS_MAX_AGE_MINUTES` (default 15) logs a WARNING naming
   the source. FR9's "diversity gate stays green on the other 4 sources"
   blind spot is closed; the check is try/except-guarded and can never
   break the cycle.

Settings/env: `sentiment_liveness_max_age_minutes` added to Settings and
`.env.example` in the same commit (env-settings-sync hook contract).

## TDD evidence

- RED-first: `tests/test_sentiment_f9h03_producer.py` (15 pins) failed at
  collection (`ImportError: cannot import name 'LKG_TTL_SECONDS'`) before
  the implementation; all four remediation parts pinned.
- GREEN: 15/15 new pins pass; full affected surface
  (`test_sentiment`, `test_sentiment_coverage`, `test_orchestrator`,
  `test_orchestrator_extra`, `test_scheduler`) **141 passed**; one legacy
  contract pin updated with citation (`cache_miss` now asserts BOTH cache
  writes — result + LKG).
- Gates: ruff (repo scope) clean, ruff format clean, isort clean, flake8
  clean, pre-commit mypy hook (strict, pyproject) **Passed**, bandit clean.
- Full-repo pytest run on the working tree: green (see PR body for the
  run stamp).

## P5 span-safety statement

No change to producer scheduling, window semantics, breaker wiring,
grader, or supervision. The remediation alters only the sentiment
producer's internal cost profile (cache hits instead of repeated
downloads), its persistence path (which previously never executed), and
adds a logging-only liveness check. The live P5 supervisor (run 140341)
is untouched: code lands on main and activates at the next restart, which
remains post-30Sep by policy. New behaviour can therefore influence the
gate only after the current grading checkpoint.
