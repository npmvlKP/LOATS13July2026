# 02Oct2026 Operator-Mandate Wave: Session Activation, Market Regime, Instrument Identification

## Mandate (operator, 02Oct2026 — mandatory in auto mode)

1. Every enabled market (NSE / MCX / Forex-CDS) working day and session
   window, the running system activates itself per segment session and
   communicates login + market-data availability through the Telegram bot
   (desktop PC running).
2. The system reports each market's status: BULL / BEAR / NEUTRAL.
3. Using sentiment analysis + volume analysis + market status, the system
   identifies candidate trading instruments per market.

## What landed

- `src/loats/market_status.py` (NEW): `MarketStatusService` +
  pydantic models (`MarketStatusReport`, `SegmentStatus`,
  `InstrumentMetrics`, `InstrumentOpportunity`, `MarketRegime`).
  - Per-segment phase gate reuses `loats.segments` session/holiday truth
    (halted / pre_open / open / closed). Outside an open session the
    segment reports honestly (no fabricated quotes) and short-circuits.
  - Regime classification is DETERMINISTIC and price-confirmed:
    1. no price leg -> NEUTRAL;
    2. volume participation < 0.8x average -> NEUTRAL (veto);
    3. |change| < 0.10% with weak/absent sentiment -> NEUTRAL (flat band);
    4. BULL: change >= +0.10% AND ensemble sentiment >= +0.15;
    5. BEAR: mirrored; strong variants at >= 0.60% / >= 0.35;
    6. price/sentiment disagreement -> NEUTRAL. Sentiment alone never
       flips a regime.
  - Instrument identification ranks per-symbol real quote metrics
    (0.5*|change| capped 2% + 0.3*|sentiment| + 0.2*volume capped 2x)
    per segment, top-3; NEUTRAL segments and vetoed symbols excluded.
    Identification is REPORT-ONLY (F8-H-03: the orchestrator remains the
    sole signal engine; no Signal rows, no decisions routed).
  - Benchmarks: NSE NIFTY (NSE_INDEX), MCX GOLD/SILVER/CRUDEOIL (MCX),
    CDS USDINR (CDS) — spellings verified present in the 01Oct
    107237-symbol master-contract download. Sentiment is the production
    VADER ensemble over the validated RSS set, one market-wide score per
    segment.
  - Activation semantics: the consolidated report is sent over Telegram
    the first time any enabled segment transitions into its open session;
    segments are marked announced ONLY after confirmed delivery, so a
    Telegram failure retries on the next tick. A restart re-announces by
    design (fresh proof of activation after redeploy).
  - Every external leg (quotes, sentiment) degrades independently to
    None/"unavailable: <reason>" — availability reporting must not die
    with a data source.
- `src/loats/openalgo.py`: `get_quotes(symbols, exchanges=None)` on both
  sync and async clients; `_quote_request_shape(symbol, exchange=None)`
  accepts an explicit exchange (MCX/CDS symbols do not exist on the NSE
  cash segment). Default behavior byte-identical: the async cache digest
  for no-exchange calls is UNCHANGED (verified by test), so the deployed
  cache namespace is not forked; explicit-exchange calls get a
  `symbols|exchanges` digest.
- `src/loats/scheduler.py`: new support job `market_activation_check`
  (IntervalTrigger 1 min) wired through the standard scan-task lifecycle
  (create/await/cancel-safe/pop). `scan_tasks` widened to
  `Task[Any]` (heterogeneous task payloads already stored).
  `run_once("market_activation_check")` supported.
- `tests/test_market_status.py` (NEW): 40-case net — every classifier
  branch, ranking/caps/exclusions, announce-once + retry-on-failed-
  delivery semantics, HTML-escape of external text, holiday/weekend
  phases (2026-10-02 Gandhi Jayanti asserted as halted), per-segment
  exchange routing, degradation legs, client compat guards.
- `tests/test_scheduler_full.py`: support-job set pin updated
  (+`market_activation_check`; still zero signal-emitting jobs).

## Verification

- Targeted suites: `tests/test_market_status.py`,
  `tests/test_scheduler_full.py`, `tests/test_segments.py`,
  `tests/test_openalgo.py` — 151 passed, 0 failed.
- Import read-back: `import loats.market_status, loats.scheduler,
  loats.openalgo` clean on the repo venv (Python 3.12.7).
- Cache-compat regression caught during the wave: the first digest shape
  (`"A,B|"`) differed from the legacy `"A,B"` payload; fixed to keep the
  no-exchange byte form and pinned by
  `test_async_default_cache_key_backward_compatible`.
- Test-authored corrections (spec-vs-test conflicts resolved in favor of
  the documented classifier contract): flat-price+strong-sentiment stays
  NEUTRAL (price-confirmation rule); delivery failure signals via
  announced-set state (v2 returns the report, not None).

## Operational notes

- 02Oct2026 is an NSE+MCX+CDS holiday (Gandhi Jayanti): all segments
  report `halted` today; the activation report fires on the next trading
  day's session open (Mon 05Oct2026 pre-open per segment schedule).
- ENABLED_SEGMENTS gates everything (default `NSE`); operators opt into
  MCX/CDS via `.env` exactly as the 01Oct segment wave documented.
- Ratchet: tree 516 -> 519 (+3: market_status.py, test_market_status.py,
  this record), ceiling 516 -> 519, entry 510.
