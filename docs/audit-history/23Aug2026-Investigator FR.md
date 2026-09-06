# LOATS13July2026 — Forensic Engineering Report (Review #7 — Investigator, CMP Conformance Re-Audit)

**Date:** 2026-08-23
**Project:** LOATS13July2026 — Lite OpenAlgo Trading System (Indian equities/options research; OpenAlgo broker API; Telegram alerts; APScheduler + orchestrator analysis pipeline)
**Repository:** https://github.com/npmvlKP/LOATS13July2026.git (HEAD `163cdf9`, 2026-08-23 10:24 IST; working tree clean)
**Python:** 3.12.7 — clean venv `G:\.OA\LOATS-13July2026\LOATS13July2026\LOATS13July2026\`
**Master plan audited against:** `LOATS-CMP-13July2026.txt` (Compact Master Plan, "LITE" edition)
**Mode:** REVIEW ONLY — no code modified, no patches generated, no destructive operations executed. Every recommendation is conditional on explicit USER APPROVAL.

**Reviewers (Senior Engineering Review Board):** Principal Software Architect · Senior Python Engineer · Senior Code Reviewer · Production Debugging Engineer · Performance Optimization Engineer · Scalability Engineer · Security Auditor · DevOps & Infrastructure Engineer · QA / Test Architect · Reliability Engineer (SRE) · Technical Lead · Systems Design Reviewer

**Evidence basis (all live, this pass, clean venv, HEAD `163cdf9`):**
`git rev-parse/log/status` (47 commits since FR6 HEAD `36d0c52`, 2026-08-16 → 08-23); `check_deps_sync.py` **PASS**; `ruff check` **PASS (0 errors)**; `ruff format --check` **PASS (132 files already formatted)**; `isort --check-only` **PASS**; `flake8` **PASS (exit 0)**; `mypy src/ --strict` **FAIL — exit 2, module-name collision, checking aborted**; `bandit` **PASS (exit 0)**; `pip-audit` **NOT RUNNABLE — module not installed in venv**; `pytest` **1123 passed / 0 failed / 1 warning, 160.35 s — coverage 76.36% → `--cov-fail-under=80` GATE FAIL (exit 1)**; empirical rate-limiter probe (singleton identity True; effective `max_ops = 3 = settings.max_ops`; **3/10** order and **3/10** smart acquires pass in a 1-second burst); per-module coverage table; source reads of `orchestrator.py`, `trade_decision.py`, `rules.py`, `strength/__init__.py`, `sizing.py` (import graph), `trailing_stop.py` (usage), `rate_limiter.py`, `settings.py`, `openalgo.py` (modification/rate-limit call sites), `Dockerfile`, `pyproject.toml`, `.github/workflows/ci.yml`, `scripts/check_per_module_coverage.py`; grep sweeps for CMP scope (signal source metadata, `set_vix_level` callers, `date.today()`, decision gates, session lifecycle, modification counters); git inventory (343 tracked files; 8 stray files directly under `src/`; 76 files in `docs/audit-history/`; 42 in `reports/ai-generated/`; root reduced to 3 `.md`).

---

## 1. Executive Summary

### 1.1 Verdict

**The project is closer to the CMP than at any prior review — but it is still NOT built strictly per `LOATS-CMP-13July2026.txt`, and current HEAD does not pass its own CI.** The 47 commits since FR6 delivered real, verifiable substance: the OPS self-limit (≤3) is now empirically enforced (F6-C-01 CLOSED), all seven orchestrator defects were fixed (F6-H-05 CLOSED), the CMP strategy modules (`rules.py`, `sizing.py`, `strength/`, `trailing_stop.py`, `trade_decision.py`, `backtest_sanity.py`, `trading_strategy/core.py`) now exist and are import-wired, position limits 5/3 are configured (Rule 11), session lifecycle exists, and Docker is hardened.

**However** — the two most important claims of this build wave are not true in the operational sense:

1. **The CMP strategy chain is unreachable at runtime.** All three production signal types carry `metadata={"source": "orchestrator"}` (`orchestrator.py:271, :338, :480`). The CMP decision engine requires **≥3 unique sources** (`strength/__init__.py:50, :379-390` — dedupes by `metadata["source"]`). Production can therefore ever supply exactly **1** unique source. `create_trade_decision` rejects at Step 1 every cycle; the gating rules → sizing → trailing → VaR → TradeDecision → Analyzer chain executes **only in tests that fabricate multi-source signals**. (F7-C-02 — Critical.)
2. **Analyzer routing is a stub.** `trade_decision.py:231-270` — `route_to_analyzer()` logs, sleeps 0.1 s, and returns a fabricated `{"status": "success", "analyzer_response": {"status": "QUEUED_FOR_ANALYSIS"}}`. Its own docstring: *"In production, this would send to actual Analyzer service. For now, we simulate."* No OpenAlgo call, no persistence. CMP P5 "route ALL TradeDecisions to Analyzer" is **simulated, not implemented** — despite commit `98e7d89` claiming "Analyzer Routing … handles API integration". (F7-H-01 — High.)

And the quality posture **regressed below the gate line again**: `mypy --strict` fails (exit 2 — `src/__init__.py` collision) and coverage fell to **76.36% < 80** (new modules are sinks: `trailing_stop` 11%, `backtest_sanity` 0%, `trade_decision` 30%). Two CI gates RED at HEAD while commits claim "FULLY COMPLIANT" (`98e7d89`), "Production Deployment Approved … READY FOR LIVE DEPLOYMENT" (`471762d`), and benchmark fixes verified (`163cdf9`). The misleading-commit pathology first flagged in R5b-F-NEW-1 and measured in F6-C-02 is now in its **fourth consecutive review**.

**NOT READY for live capital. ANALYZE-mode demo only — and current HEAD fails its own CI.**

### 1.2 CMP demand vs build reality (verified live this pass)

| CMP requirement | State at HEAD `163cdf9` | Verdict |
|---|---|---|
| LITE: zero services, pip-only | SQLite WAL + JSONL audit; custom `threading.Lock` TTL cache (redis ghost import deleted); stdlib metrics | ✅ Conformant |
| Pipeline: Sentiment → TA/VA → **Strength** → **Rules** → Strike → Risk → Orchestrator | All modules exist and are import-wired (`orchestrator.py:21,25` → `trade_decision.py:20-23` → rules/sizing/strength/trailing_stop) | ✅ Structurally present — **but dead at runtime (F7-C-02)** |
| **Rule 4: OPS threshold 10; self-limit ≤3** | **EMPIRICALLY ENFORCED**: probe — singleton identity True, `effective max_ops: 3`, `settings.max_ops: 3`, **3/10 acquires pass**; factories default from settings (`rate_limiter.py:36,149,180`); call sites bare (`openalgo.py:820,897`) | ✅ **FIXED (F6-C-01 closed)** |
| Rule 7: modification limit **25**/order | `openalgo.py:514` enforces 25 (hard-coded); **but `settings.py:99` declares `max_modifications=30` labeled "CMP Rule 7: ≤30"** — wrong value, dead knob; counters in-memory, fail-open, reset on restart | 🟠 Partial + mislabeled |
| Rule 8: `as_of_date`; never `date.today()` | Zero `date.today(` matches; `as_of_date` convention still absent | 🟡 Half (unchanged) |
| Rule 9: py_vollib; newspaper4k; VADER ±0.05 | `vollib` (documented successor, `VOLLIB_MIGRATION_PLAN.md`); newspaper4k ✅; `sentiment_threshold=0.05` ✅ | 🟡 Documented deviation (carried) |
| Rule 10: India VIX = external input | `rules_engine.set_vix_level()` exists — **zero production callers** (grep: definition only). Gate always uses fallback **18.5** | 🔴 **Input never wired (F7-H-02)** |
| Rule 11: position limits 5 NIFTY / 3 BANKNIFTY | `max_nifty_positions=5`, `max_banknifty_positions=3` (`settings.py:104-109`); legacy 1000s retained as generic fallback | ✅ Fixed |
| Rule 12: trailing = monotonic ratchet; SL-M | `trailing_stop.py` (545 stmts) exists; `initialize_trailing_stop` called once at decision time (`trade_decision.py:145`); **ratchet update/monitor logic has zero production callers** — SL-M never moves after entry | 🟠 Partial (engine dormant) |
| P2 gate: BBANDS 20, CCI 20, Hurst, ADX, regime | `calculate_bbands` / `calculate_cci` / `calculate_hurst_exponent` / `calculate_adx_standalone` (`ta.py:385,414,447,546`) + strength integration | ✅ Implemented |
| P2 strength composite | `strength/` package with per-source weights, opposition gate 0.4, min_sources 3 | ✅ Implemented — **starved of sources at runtime** |
| P4: rules gates (IV-rank/ADX/VIX), 2% sizing, trailing, VaR, backtest | Rules gates real (`rules.py:205-286`); 2% fixed-frac sizing ✅ (`sizing_engine.calculate_fixed_fraction_size`); VaR ✅ (`options.calculate_portfolio_var`); **BUY gate uses IV-rank < 60, CMP says < 30** (`rules.py:256-257`); `backtest_sanity.py` **0% covered, never invoked in prod** | 🟠 Partial (F7-M-01, F7-H-03) |
| P5: 3 gates, per-source breakers, session lifecycle, ALL decisions → Analyzer, 2-wk forward test | Session lifecycle ✅ (`rules.py:37-62`); 0.6/0.4 thresholds ✅; **routing simulated**; per-source breakers ❌ (global only); forward test: no evidence | 🟠 ~60% (F7-C-02, F7-H-01) |
| Verification gates (ruff, mypy --strict, bandit, cov ≥80, pip-audit) | ruff/format/isort/flake8/bandit/deps-sync ✅ — **mypy 🔴 (collision), coverage 🔴 76.36%, pip-audit unverifiable** | 🔴 Gates red at HEAD (F7-C-01) |
| Repo structure per CMP §4 | Flat `src/loats/` retained; `connectors/`, `risk/manager/`, `strategy/rules/` created as **empty ~170-byte `__init__.py` shells** (structure theater); 8 stray files directly in `src/` incl. `src/__init__.py` (the mypy breaker), `test_cmp*.py`, probe scripts | 🟠 Deviation + F7-M-06 |
| Git hygiene (compact repo) | Root cleaned (3 `.md`), `.env` untracked ✅ — but repo **grew** 302 → **343 tracked** (76 `docs/audit-history/` + 42 `reports/ai-generated/` files) | 🟡 Mixed |

Full clause-by-clause matrix: **Appendix A**. FR6 disposition: **Appendix B**.

### 1.3 Scorecard across the review chain

| Dimension | FR5 (08Aug) | FR6 (15Aug) | **FR7 (23Aug, this)** | Trend |
|---|---|---|---|---|
| Tests | 640/0 | 843/0 | **1123/0** | ✅ Up |
| Coverage (aggregate) | 80.10% | 80.43% | **76.36% — GATE FAIL** | 🔴 Regressed |
| Ruff | 0 | 135 | **0** | ✅ Recovered |
| Ruff format / isort | clean | 20 / 11 dirty | **clean / clean** | ✅ Recovered |
| Mypy `--strict` | 0 | 0 (27 files) | **FAIL exit 2 (collision — checking aborted)** | 🔴 Regressed |
| Flake8 / bandit / deps-sync | mixed | clean | **clean** | ✅ Held |
| pip-audit | pass | pass | **NOT RUNNABLE (absent from venv)** | 🟡 Unverifiable |
| Order-path OPS ≤3 | broken | singleton @ 50 | **3 enforced (empirical)** | ✅ **FIXED** |
| Orchestrator defects (7) | n/a | 7 open | **0 open (all 7 verified fixed)** | ✅ Fixed |
| CMP strategy core | absent | absent | **present + wired, but runtime-dead (source gate) + routing stub** | 🟠 Half-real |
| Commit claims vs reality | false | false | **false again ("FULLY COMPLIANT", "READY FOR LIVE DEPLOYMENT")** | 🔴 4th review running |

### 1.4 The three things that matter most

1. **F7-C-01 (Critical, process):** HEAD fails its own CI — mypy (exit 2) and coverage (76.36% < 80). The final commits of the wave (08-22/23) claim full compliance and verified fixes; the gates contradict them within hours. Branch protection on `main` (recommended in FR5/FR6) was never enabled.
2. **F7-C-02 (Critical, conformance):** the CMP strategy chain cannot execute in production — every signal's `source` is `"orchestrator"`, the ≥3-unique-source gate can never pass, so `create_trade_decision` rejects at Step 1 forever. The conformance evidence (tests) works only because tests fabricate 3-source signals. Fix = tag signals with real source identities (ta / sentiment / market-data / options-flow) — a small change, but until then "CMP strategy implemented" is true only of the code path, not the system.
3. **F7-H-01 + F7-H-02 (High, conformance):** Analyzer routing is a simulated stub, and the VIX gate runs on a hard-coded 18.5 fallback that permanently blocks BUY (18.5 ≮ 15) and vacuously passes SELL — meaning even if the source gate were fixed, the system could only ever emit SELL decisions, and those decisions would go nowhere (stub routing).

---

## 2. Architecture Overview

```
src/loats/                              # importable package (hatch wheel target)
├── __init__.py                         # PEP 562 lazy settings; initialize_system()
├── initialization.py / loats_logging.py# logging bootstrap; structlog-first
├── metrics.py                          # stdlib ThreadingHTTPServer :8001 + in-memory stats
├── config/                             # lazy Settings; __all__=[Settings, get_settings]
├── models.py                           # Pydantic v2; TradeDecision, VaRResult, SL_M, session enum
├── database.py                         # sqlite3 WAL + JSONL-first audit + aiosqlite pool
├── database_async_additions.py         # monkey-patch true-async aiosqlite methods (71% cov)
├── openalgo.py                         # sync+async clients; kill switch; CB all paths; Idempotency-Key;
│                                       #   Rule 7 modification gate (25, hard-coded); OPS limiters (3)
├── alerts.py                           # Telegram v20+; admin allow-list; html.escape
├── scheduler.py                        # APScheduler; IST + NSE holidays; shared db singleton
├── orchestrator.py                     # 100ms cycle; parallel TA/sentiment/market window (80ms);
│                                       #   legacy 2-source signal path + _execute_cmp_strategy()
├── rules.py                            # NEW: session lifecycle; IV-rank/ADX/VIX gates;
│                                       #   modification counters; position limits; loss streaks
├── strength/                           # NEW: per-source weights, composite, opposition gate 0.4,
│                                       #   min_sources=3, validate_signal_sources
├── sizing.py                           # NEW: 2% fixed-fractional, cost+margin aware
├── trailing_stop.py                    # NEW: ratchet engine (545 stmts — 11% covered, dormant)
├── trade_decision.py                   # NEW: CMP decision workflow; SIMULATED Analyzer routing
├── backtest_sanity.py                  # NEW: walk-forward sanity (0% covered, no prod caller)
├── trading_strategy/core.py            # NEW: strategy facade (91%)
├── performance_analyzer.py             # NEW: benchmark harness (97%)
├── strike_selection.py / sentiment.py / ta.py / options.py
└── utils/                              # cache (threading.Lock TTL), circuit_breaker, connection_pool,
                                        #   payload_builder, rate_limiter (settings-wired, 3 OPS),
                                        #   resilience, retry

src/                                    # ⚠ STRAY LAYER: __init__.py (mypy breaker), cmp.py,
                                        #   probe_rate_limiter.py, test_cmp*.py ×3, utils.py, var_engine.py
src/loats/{connectors,risk,risk/manager,strategy,strategy/rules}/
                                        # ⚠ EMPTY SHELLS (~170-byte __init__.py each)
```

**Runtime lifecycle:** `TradingSystem.initialize()` → metrics server → `db.async_initialize()` + audit verify → alerts/scheduler init → `start()` → `alerts.start()` + `scheduler.start()` + `start_orchestrator()` → cycle loop every ~100 ms: parallel (TA ‖ sentiment ‖ market-data, 80 ms budget) → legacy `_execute_signal_generation()` → `_execute_risk_management()` → `_execute_cmp_strategy()` (session-gated) → shutdown: real drain (`await asyncio.wait_for(self._cycle_task, 5.0)` + cancel), scheduler, alerts, `async_close_all()`.

**Architectural deltas since FR6 (verified):**
1. **Strategy layer added** (rules/strength/sizing/trailing_stop/trade_decision/backtest_sanity/trading_strategy) — import-wired into orchestrator and openalgo (Rule 7 gate).
2. **Two parallel signal engines now coexist**: the legacy 2-source combiner (`orchestrator.py:441-486`, threshold 0.6, stores to DB every cycle) and the CMP chain (`:609+`, reads those same signals, requires ≥3 unique sources). The legacy path feeds the DB the CMP path then starves on. (F7-M-04.)
3. **Rate limiter re-wired to Settings** — class ctors and factories both default from `settings.max_ops` (F6-C-01 closed).
4. **Cache rewritten** as a custom `threading.Lock` TTL cache (redis ghost import gone — F6-L-02 closed, R5-F-04 fully closed).
5. **Docker hardened**: multi-stage, `pip install --no-deps .`, non-root `USER loats` (F6-M-07 closed).
6. **`src/__init__.py` + stray `src/*.py` introduced** — the direct cause of the mypy gate failure (F7-C-01a).

---

## 3. Reverse Engineered Data Flow

```
              ┌─────────────────────── TradingSystem (main.py) ────────────────────────┐
              │  metrics :8001    alerts (Telegram)    scheduler (NSE-holiday-aware)   │
              └──────────────────────────────┬─────────────────────────────────────────┘
                                             │
           orchestrator._run_cycle_loop (100 ms budget, kill-switch gated, alert backoff 1/min)
                     │
     ┌───────────────┴────────────────┐
     ▼                                ▼
 LEGACY PATH (runs every cycle)      CMP PATH (session-gated, runs every cycle)
 _execute_signal_generation          _execute_cmp_strategy (:609)
   ta signal   source="orchestrator"   db.async_get_latest_signals (≤10, last 5 min)
   sentiment   source="orchestrator"   → validate ≥3 UNIQUE sources ──► ALWAYS FAILS (1 unique)
   combined    source="orchestrator"   │   (strength/__init__.py:379-390, min_sources=3)
   → stored to DB                      └── gating → 2% sizing → trailing init → VaR
                                          → TradeDecision → route_to_analyzer (SIMULATED:
                                          log + sleep(0.1) + fabricated success)   [DEAD at runtime]
                     │
                     ▼
 AsyncOpenAlgoClient — kill switch → OPS limiter (3/s, empirical) → CB fail-fast
                     → Idempotency-Key (UUID v4; cancel/modify keyed by order_id;
                       place by payload digest) → Rule 7 gate (≤25, hard-coded)
                     │
                     ▼
 db.async_* (aiosqlite pool → to_thread fallback) → SQLite WAL + JSONL audit
   (JSONL-first canonical SHA-256; ⚠ PYTEST_CURRENT_TEST bypass still at database.py:774)
```

**Order path (financial-critical), verified line-level this pass:** `place_order` → `_async_check_kill_switch()` → `get_order_rate_limiter().acquire()` (`openalgo.py:820` — **defaults from settings, 3/s**) → Rule 7 modification gate for modify (`:514`, limit=25) → CB open-check → `_request(..., idempotency_key=...)` → `Idempotency-Key` header + DB duplicate-order guard. Kill-switch blocks audited.

**Async boundary:** orchestrator/scheduler/alerts on one event loop; aiosqlite pool spans worker threads; legacy sqlite3 via `to_thread`; RSS/newspaper via `to_thread`+`gather`. TA analysis now runs **inside** the 80 ms parallel window (`orchestrator.py:169-184`) with cancel-on-timeout — F6-H-05.7 fixed.

---

## 4. Dependency Overview

| Dependency | pyproject | requirements-core | Verdict |
|---|---|---|---|
| Core set (httpx, pydantic(-settings), APScheduler, numpy, pandas, scipy, vaderSentiment, feedparser, newspaper4k, structlog, python-telegram-bot, python-dotenv, cachetools-replacement, aiosqlite, lxml, lxml-html-clean, cryptography) | ✅ | ✅ | ✅ Synced — `check_deps_sync.py` PASS (gate-enforced) |
| `vollib>=1.0.11` | ✅ | ✅ | 🟡 CMP rule 9 says `py_vollib`; documented successor deviation (carried, VOLLIB_MIGRATION_PLAN.md); mypy override `module = "vollib.*"` |
| `ta` dependency | ✅ | ✅ | 🟡 Still declared; custom `ta.py` used — drop or adopt (carried) |
| **pip-audit** (dev extra) | ✅ declared | ✅ declared | 🔴 **Not installed in the clean venv** — `python -m pip-audit` → `No module named pip-audit`. Gate unverifiable this pass. Not enough evidence that the dependency-audit gate passes at HEAD. |

External integrations: OpenAlgo REST, Telegram Bot API, RSS feeds. **VIX has no feed** (F7-H-02).

---

## 5. Module-by-Module Review

Coverage from this pass's live run (1123 tests, branch coverage on):

| Module | Stmts | Cover | Verdict | Key notes |
|---|---|---|---|---|
| `utils/payload_builder.py` | 54 | **100%** | ✅ | Shared order-payload builder |
| `src/var_engine.py` ⚠ stray | 196 | **100%** | 🟠 | 100% covered — but lives OUTSIDE the package, directly in `src/` |
| `loats_logging.py` | 20 | **100%** | ✅ | structlog-first |
| `initialization.py` | 6 | **100%** | ✅ | |
| `performance_analyzer.py` | 180 | 97% | ✅ | NEW benchmark harness |
| `config/settings.py` | 85 | 96% | ✅ | `max_ops=3` wired; **`max_modifications=30` mislabeled as CMP Rule 7** |
| `sizing.py` | 127 | 96% | ✅ | NEW; 2% fixed-fractional |
| `strength/config.py` | 45 | 96% | 🟠 | NEW |
| `trading_strategy/core.py` | 160 | 91% | ✅ | NEW facade |
| `models.py` | 262 | 92% | ✅ | TradeDecision/VaRResult/session enums |
| `rules.py` | 169 | 92% | ✅ | NEW; gates + session + counters; **BUY IV-rank 60 vs CMP 30; VIX fallback 18.5** |
| `sentiment.py` | 109 | 93% | ✅ | VADER ±0.05 |
| `utils/circuit_breaker.py` | 141 | 99% | ✅ | |
| `utils/connection_pool.py` | 74 | 91% | ✅ | Pool lifecycle fixed (F6-H-03 partly closed) |
| `utils/resilience.py` | 87 | 89% | ✅ | |
| `main.py` | 124 | 88% | ✅ | Metrics + orchestrator wired |
| `ta.py` | 401 | 87% | ✅ | ADX/BBANDS/CCI/Hurst added |
| `openalgo.py` | 411 | 87% | ✅ | Order paths covered; Rule 7 gate |
| `utils/retry.py` | 89 | 87% | ✅ | |
| `utils/rate_limiter.py` | 212 | 84% | ✅ | **Settings-wired, 3 OPS enforced** |
| `utils/cache.py` | 269 | 85% | ✅ | threading.Lock TTL cache |
| `metrics.py` | 183 | 85% | ✅ | |
| `database.py` | 597 | 79% | 🟠 | **PYTEST_CURRENT_TEST JSONL bypass still present (:774)** |
| `alerts.py` | 478 | 79% | 🟠 | Broad except paths untested |
| `scheduler.py` | 371 | 76% | 🟠 | Job-error paths untested |
| `database_async_additions.py` | 225 | 71% | 🟠 | Up from 31% (F6-H-03 improved); teardown warnings gone from live run (1 benign warning total) |
| `orchestrator.py` | 457 | 67% | 🔴 | **CMP strategy body (:638-737) untested** — the runtime-dead path is also the untested path |
| `strike_selection.py` | 211 | 66% | 🟠 | |
| `options.py` | 343 | 66% | 🔴 | **Regression 90% → 66%** — VaR/Greeks edge paths untested |
| `trade_decision.py` | 127 | **30%** | 🔴 | NEW; **routing/queue/persist bodies untested** |
| `backtest_sanity.py` | 159 | **0%** | 🔴 | NEW; CMP P4 gate module — **zero tests, zero production callers** |
| `trailing_stop.py` | 270 | **11%** | 🔴 | NEW; ratchet logic untested and never invoked at runtime |

---

## 6. Critical Findings (Priority P0)

### 🔴 F7-C-01 — HEAD fails its own CI: mypy gate broken (module collision) + coverage gate broken (76.36% < 80)

- **Issue ID:** F7-C-01
- **Category:** Process / Quality Gates
- **Severity:** Critical (blocks merge; contradicts commit claims) · **Confidence:** Certain (live runs, this pass)
- **Owning specialists:** Technical Lead, QA / Test Architect, DevOps & Infrastructure Engineer
- **Evidence (clean venv, HEAD `163cdf9`):**
  - `mypy src/ --strict --config-file pyproject.toml` → **exit 2**: `"Source file found twice under different module names: 'src.loats.utils.rate_limiter' and 'loats.utils.rate_limiter' … errors prevented further checking."` CI (`ci.yml` "Run MyPy" step) runs the **same command** → CI mypy job RED.
  - **Root cause (new this wave):** `src/__init__.py` now exists (added by the "missing package structure" commit `98e7d89`), making `src` itself a package. Mypy crawling `src/` then computes `src.loats.*` module names while the package imports resolve as `loats.*` → collision, checking aborted. Zero type errors were even reported — the gate fails before checking.
  - `pytest tests/ --cov=src --cov-branch --cov-fail-under=80` → **1123 passed / 0 failed, coverage 76.36% → FAIL (exit 1)**. CI runs the same gate (`ci.yml:84-93`). The aggregate dropped 80.43% → 76.36% because the new strategy modules arrived untested (trailing_stop 11%, backtest_sanity 0%, trade_decision 30%, orchestrator CMP body untested, options.py regressed 90% → 66%).
  - `pip-audit`: **cannot run** — module absent from the clean venv (declared in dev extras). Gate state at HEAD: **not enough evidence** (see Appendix D).
  - Contrast (same tree): deps-sync ✅, ruff ✅ (0 errors), ruff-format ✅ (132 files), isort ✅, flake8 ✅, bandit ✅.
  - Commit claims contradicted by the tree: `98e7d89` (08-22) "__System now fully complies with CMP Rule 4__ … All existing tests continue to pass"; `471762d` (08-20) "__Production Deployment Approved … Final Status: ✅ READY FOR LIVE DEPLOYMENT__"; `163cdf9` (08-23, HEAD) verification claims with no gate re-run. This is the **fourth consecutive review** documenting the misleading-commit pathology (R5b-F-NEW-1 → F6-C-02 → F7-C-01).
- **Root cause:** Structural change (`src/__init__.py`) shipped without re-running CI; large new modules shipped without tests; branch protection / required status checks on `main` still not enabled (recommended in FR5 §21 and FR6 §21 — never actioned).
- **Impact / possible consequences:** CI red at HEAD — no merge or release possible from this state; `git log` again gives false confidence; untested financial-decision code (sizing, trailing, VaR, routing) counts as "verified" in commit messages.
- **Risk assessment:** Critical (process).
- **Suggested resolution (pending approval):** (a) delete `src/__init__.py` (and relocate the 8 stray `src/*.py` files — see F7-M-06) and re-run mypy; (b) raise coverage on the new modules to ≥80% per-module (start with `trailing_stop`, `trade_decision`, `backtest_sanity` — or exclude-with-justification if any is intentionally dormant); (c) install dev extras fully in the venv and re-run pip-audit; (d) **enable branch protection requiring CI on `main`** — fourth time asking; (e) commit-message discipline: enforce the existing `commit_message_check.py` hook.
- **Estimated complexity:** Low-Medium (a+b ≈ 1 day; c+d+e ≈ 30 min). **Dependencies:** none. **Priority:** **P0**.

### 🔴 F7-C-02 — CMP strategy chain is unreachable at runtime: every signal's source is "orchestrator", the ≥3-unique-source gate can never pass

- **Issue ID:** F7-C-02
- **Category:** CMP Conformance / Correctness (financial decisioning)
- **Severity:** Critical · **Confidence:** Certain (line-level source evidence + logic trace)
- **Owning specialists:** Principal Software Architect, Production Debugging Engineer, Systems Design Reviewer, QA / Test Architect
- **Evidence:**
  - Signal creation sites (all three, `src/loats/orchestrator.py`):
    - `:271` — TA signal: `metadata={"scan_type": "ta", "source": "orchestrator"}`
    - `:336-340` — sentiment signal: `metadata={"scan_type": "sentiment", "source": "orchestrator", ...}`
    - `:478-484` — combined signal: `metadata={"scan_type": "combined", "source": "orchestrator", ...}`
  - Validation (`src/loats/strength/__init__.py:379-390`): `source_set = {signal.metadata.get("source", "unknown")}` → `if len(source_set) < self.min_sources` (min_sources = 3, `:50`) → reject `"insufficient_unique_sources"`.
  - Production `source_set` = `{"orchestrator"}` → size 1 < 3 → **`create_trade_decision` returns `(None, rejected)` at Step 1 on every cycle, forever.** The downstream chain (composite strength → gating rules → position limits → 2% sizing → trailing init → VaR → TradeDecision → routing) executes **only in tests**, which fabricate signals with varied `source` strings.
  - Commit `98e7d89` claims the "Trading-Strategy Core" is "Properly Wired"; `92b99f2` claims "~100% phase completion" for P4/P5. The wiring is import-level only — the runtime path is dead.
- **Root cause:** The CMP P5 requirement (≥3 **sources**) was implemented as a gate over `metadata["source"]`, but the signal producers were never taught to identify themselves as distinct sources (ta / sentiment / market-data / options-flow). The strength engine even defines weights for `PRICE_ACTION`, `VOLATILITY`, `FUNDAMENTAL`, `MACHINE_LEARNING`, `OPTIONS_FLOW` (`strength/__init__.py:41-47`) — **no production producer exists for any of them**.
- **Technical explanation:** A gate that its own feedstock can never satisfy is indistinguishable from a disabled system. All conformance evidence for the CMP chain is therefore test-fabricated, not system-derived.
- **Impact / possible consequences:** The system cannot produce a TradeDecision in production. Any operator reading the CMP Conformance Report or commit log believes a decisioning engine is running; in reality the orchestrator logs "Insufficient signals" at debug level every cycle (silently — it is `logger.debug`, `orchestrator.py:631`).
- **Risk assessment:** Critical (conformance claim vs reality; silent no-op of the system's core mandate).
- **Suggested resolution (pending approval):** Tag each producer with a real source identity (`"source": "ta"`, `"source": "sentiment"`, `"source": "market_data"`), implement at least a third real producer (market-data/momentum or options-flow), and add an end-to-end test that drives the **real** orchestrator signal path (not fabricated Signal objects) through `create_trade_decision`. Elevate the insufficient-signals log to INFO/WARNING with a periodic counter.
- **Estimated complexity:** Low-Medium (tagging: hours; third real producer: 1-2 days; e2e test: ½ day). **Dependencies:** none. **Priority:** **P0**.

---

## 7. High Priority Findings (Priority P1)

### 🟠 F7-H-01 — Analyzer routing is a simulated stub; no decision ever leaves the process

- **Issue ID:** F7-H-01 · **Category:** CMP Conformance (P5) / Financial Safety · **Severity:** High · **Confidence:** Certain
- **Evidence:** `trade_decision.py:231-270` — docstring: *"In production, this would send to actual Analyzer service. For now, we simulate the routing and return success."* Body: builds `to_analyzer_payload()`, **logs it, `await asyncio.sleep(0.1)`, returns fabricated** `{"status": "success", "analyzer_response": {"status": "QUEUED_FOR_ANALYSIS", ...}}`. No OpenAlgo call, no DB persist of the decision, no Analyzer-mode submission. Commit `98e7d89` claims "`TradeDecisionEngine.route_to_analyzer()` handles API integration" — **false**.
- **Root cause:** Interface completed ahead of integration; commit message described the interface as the integration.
- **Impact:** Even with F7-C-02 fixed, decisions would terminate in a log line. CMP P5 gate "route ALL Trade Decisions to Analyzer Mode" unmet; the "2-wk forward test" gate (P5) cannot even begin.
- **Suggested resolution:** Implement routing via the existing `AsyncOpenAlgoClient` in ANALYZE mode (place a paper order / analysis request per decision) AND persist every TradeDecision + routing result to SQLite/JSONL audit. Add an integration test asserting a routing side-effect exists (HTTP call or audit row).
- **Estimated complexity:** Medium (4-8 h). **Dependencies:** F7-C-02. **Priority:** **P1**.

### 🟠 F7-H-02 — India VIX input never wired; 18.5 fallback permanently blocks BUY and vacuously passes SELL (CMP Rule 10)

- **Issue ID:** F7-H-02 · **Category:** CMP Conformance / Correctness · **Severity:** High · **Confidence:** Certain
- **Evidence:** `rules.py:187-196` — `get_vix_level()` returns `self._vix_level` or **18.5 "Neutral default"**. `set_vix_level()` (`:198`) has **zero production callers** (repo-wide grep: definition and docstring only). Gating (`:231-259`): SELL requires `vix > 15` → 18.5 always passes; BUY requires `vix < 15` → 18.5 always fails.
- **Root cause:** Rule 10 ("India VIX = external input, never derived") was honored in shape (setter exists, nothing derives VIX) but never connected to a feed; the "neutral" default was chosen without checking its gate consequences.
- **Impact:** A so-called neutral default is structurally **anti-BUY / pro-SELL-eligible**. If F7-C-02 is fixed, the system could only ever emit SELL decisions. VIX-based risk-off protection (VIX>15) is decorative.
- **Suggested resolution:** Wire an external VIX source (OpenAlgo quote for the India VIX symbol, cached) into `set_vix_level()` on the market-data task; fail-safe behavior should be configurable and *symmetric* (e.g., no-feed ⇒ treat VIX gate as failed for BOTH directions, or as explicitly-unknown and logged).
- **Estimated complexity:** Low-Medium (2-4 h). **Dependencies:** none. **Priority:** **P1**.

### 🟠 F7-H-03 — New financial-decision modules shipped untested; aggregate coverage below gate (trailing 11%, backtest 0%, trade_decision 30%; options.py 90%→66%)

- **Issue ID:** F7-H-03 · **Category:** Testing / Risk · **Severity:** High · **Confidence:** Certain (live coverage table)
- **Evidence:** `trailing_stop.py` 11% (229/270 missed — the ratchet math itself), `backtest_sanity.py` 0% (159 missed — the CMP P4 gate module, also zero production callers), `trade_decision.py` 30% (routing/queue/persistence bodies), `orchestrator.py` 67% with the CMP body `:638-737` untested, `options.py` regressed 90% → 66%. Aggregate 76.36% → CI gate fail.
- **Root cause:** Build wave prioritized module creation over verification; the per-module advisory gate (F6-M-03, hardened to exit non-zero per `check_per_module_coverage.py:19,64,74,108`) was evidently not run before the final commits.
- **Impact:** The code that decides position size, stops, and VaR — the highest-consequence logic in the repo — has the least test evidence. Untested + runtime-dead (F7-C-02) means defects there are invisible twice over.
- **Suggested resolution:** Test targets per module ≥80%: ratchet monotonicity property tests (never loosen), sizing edge cases (zero funds, huge spread), VaR vs known distributions, routing failure paths. Re-run `check_per_module_coverage.py` in CI as blocking.
- **Estimated complexity:** Medium (1-2 days). **Dependencies:** none. **Priority:** **P1**.

### 🟠 F7-H-04 — Trailing ratchet never operates at runtime: initialized once, never updated (CMP Rule 12 partial)

- **Issue ID:** F7-H-04 · **Category:** CMP Conformance / Reliability · **Severity:** High · **Confidence:** Certain
- **Evidence:** `trailing_stop_engine` has exactly one production call site — `trade_decision.py:145` `initialize_trailing_stop(...)` (config creation). No scheduler job, no orchestrator step, no order path calls any update/monitor method (repo grep). The monotonic-ratchet enforcement (the actual Rule 12 behavior — SL-M ratchets as price moves) is never executed. 11% coverage matches: only init is exercised.
- **Root cause:** Rule 12 implemented as a library, not as a subsystem — no runtime driver.
- **Impact:** Stops configured at entry never trail. For a bot-logic trailing system (bracket orders disabled per Rule 6), this means the core exit-protection mechanism does not exist operationally.
- **Suggested resolution:** Add a monitor (orchestrator risk step or APScheduler job) that, per open position, fetches price, calls the ratchet update, and (in ANALYZE mode) routes the resulting SL-M modification through the Rule 7-gated `modify_order` path. Pair with F7-H-01 persistence.
- **Estimated complexity:** Medium (1 day). **Dependencies:** F7-H-03 (tests), Rule 7 counter persistence (F7-M-02). **Priority:** **P1**.

---

## 8. Medium Priority Findings (Priority P2)

- **🟡 F7-M-01 — BUY gate IV-rank threshold 60 vs CMP 30** — CMP §strategy/rules: "buy: IV rank<30". `rules.py:256-257`: `# BUY rules: IV-rank < 60 …` `iv_pass = iv_rank < 60`. SELL gate matches CMP (>40). The BUY band is double the CMP specification — buys would be permitted in IV regimes the plan classifies as sell-side. Fix: `< 30`. Certain; 1 line + tests. P2.
- **🟡 F7-M-02 — `Settings.max_modifications = 30` labeled "CMP Rule 7: ≤30"; CMP mandates 25; the live gate is a hard-coded 25** — `settings.py:99-101` vs `openalgo.py:514` (`limit=25`). The settings knob is dead (never read by the gate) AND wrong (30 ≠ 25). Commit `042a006` even states "Proper enforcement of 30 modification limit (CMP Rule 7)" — the wrong value is codified in history. Also: counters are an in-memory dict (`rules.py:396-397`), lazily created, fail-open (`:419-420` `return True  # No tracking yet`), and reset on restart — a restart resets an order's modification budget; not audit-grade. Fix: set 25, wire the gate to the setting, persist counters (SQLite), fail-closed. P2 · Medium.
- **🟡 F7-M-03 — Module-level eager `settings = get_settings()` in 10 modules** — `alerts.py:37`, `main.py:19`, `scheduler.py:36`, `sentiment.py:22` (legacy) plus **all new strategy modules**: `rules.py:22`, `sizing.py:21`, `strength/__init__.py:20`, `trade_decision.py:26`, `trading_strategy/core.py:23`, `backtest_sanity.py:26`. The NEW-L2/F6-H-05.2 anti-pattern was fixed in `orchestrator.py` (lazy, `:162-165`) and simultaneously reintroduced everywhere else. Importing any of these without `OPENALGO_API_KEY` set crashes at import time. Fix: lazy accessor per module. P2 · Low effort.
- **🟡 F7-M-04 — Dual signal engines: legacy 2-source combiner still runs every cycle alongside the CMP chain** — `orchestrator.py:187` `_execute_signal_generation()` (2-source average, 0.6/0.4 thresholds, `:441-486`) writes the very DB signals the CMP path then rejects. Two thresholds coexist (legacy 0.6; trade_decision 0.5 minimum at `trade_decision.py:88`). Confusion risk: which engine is "the" signal source of record? Fix: either retire the legacy combiner or make it the TA+sentiment producers **with real source tags** (feeds F7-C-02 fix). P2.
- **🟡 F7-M-05 — Audit JSONL write still bypassed under pytest (F6-M-01 NOT fixed despite claim)** — `database.py:774`: `if os.environ.get("PYTEST_CURRENT_TEST"):` skip. Commit `a03047e` claims "F6-M-01 … kill the PYTEST_CURRENT_TEST bypass" — the bypass is still present at HEAD. The JSONL-first dual-write guarantee remains untested by the suite. P2 · Low.
- **🟡 F7-M-06 — `src/` stray layer: 8 tracked files outside the package + empty package shells** — `src/__init__.py` (breaks mypy — root cause of F7-C-01a), `cmp.py`, `probe_rate_limiter.py`, `test_cmp.py`, `test_cmp_conformance.py`, `test_cmp_ops_threshold.py`, `utils.py`, `var_engine.py` (test/probe scripts at the `src/` level; `var_engine.py` even counts in coverage). Plus `connectors/`, `risk/`, `risk/manager/`, `strategy/`, `strategy/rules/` exist as ~170-byte empty `__init__.py` shells — CMP §4 structure theater without content. Fix: move scripts to `scripts/`/`tests/`, delete `src/__init__.py`, delete or populate shells. P2 · Low.
- **🟡 F7-M-07 — `options.py` coverage regression 90% → 66%** — VaR/Greeks edge paths untested precisely when VaR became a pre-trade input (`trade_decision.py` imports `calculate_portfolio_var`). Fold into F7-H-03 remediation. P2.
- **🟡 F7-M-08 — Repo grew to 343 tracked files (302 → 343) while "cleanup" was claimed** — root cleaned (3 `.md`, good), but 76 files under `docs/audit-history/` (incl. `debug_*.py`, `fix_test_imports.py`, `test_redis_cache.py` — old scripts with `src.loats` imports) + 42 under `reports/ai-generated/` are now tracked. Hygiene moved, not removed; ruff/mypy must exclude or carry them. P2 · Low.

---

## 9. Low Priority Findings (Priority P3)

- **🟢 F7-L-01 — Ruff ignore list still broad (20 rules)** — `pyproject.toml [tool.ruff.lint] ignore` includes `F401` (unused imports unchecked), `I001` (redundant with isort gate but still), `E402`, `PTH123`, `N803/N806`, `INP001`, `PGH003` (blanket type: ignore), `RUF005/006/012/015/022/059`. Commit `a03047e` claimed F6-M-05 "shrink ruff ignore list"; the list is still large (duplicates removed at best). Local runs under-report relative to a strict config. P3.
- **🟢 F7-L-02 — pip-audit absent from clean venv** — declared dev extra not installed; gate unverifiable (also listed under F7-C-01c). P3 (environment), P0-adjacent for gate honesty.
- **🟢 F7-L-03 — Strength source weights defined for sources that do not exist** — `FUNDAMENTAL 0.1`, `MACHINE_LEARNING 0.3`, `OPTIONS_FLOW 0.2` (`strength/__init__.py:45-47`) — dead configuration until producers exist (ties into F7-C-02 fix). P3.
- **🟢 F7-L-04 — `check_per_module_coverage.py` still ends `sys.exit(0)` at :113** — hardened with several `exit(1)` paths (:19,64,74,108) since FR6, but the final success-path exit(0) after "FAILED (warnings detected)"-style flows could not be fully traced this pass — mark for verification when F7-H-03 lands. Likely improved. P3.
- **🟢 F7-L-05 — CMP phase-gate evidence still absent** — P1 "live ANALYZE round trip" and P5 "2-wk forward test" have no run-log evidence on disk (carried from FR6 Appendix D). P3.
- **🟢 F7-L-06 — `backtest_sanity.py` has zero production callers** — the CMP P4 exit gate ("backtest sanity on /history data") is a module without a driver; even if tested, nothing invokes it. P3 (fold into F7-H-03/F7-H-04 driver work).
- **🟢 F7-L-07 — Pytest run emits 1 benign warning** (down from 9 at FR6 — aiosqlite teardown warnings and mock-misuse warnings resolved). P3.

---

## 10. Performance Review

| Item | Status | Evidence |
|---|---|---|
| Cycle <100 ms | Instrumented; structure now sound | TA inside 80 ms parallel window with `wait_for` + cancel (`orchestrator.py:169-184`); adaptive sleep; unvalidated against live data |
| Strike <5 ms | Instrumented | 4 ms `wait_for` + fallback; strike cache now bounded (TTLCache per F6-M-04 fix) |
| Trail <1 ms | ❌ N/A at runtime | Ratchet never driven (F7-H-04) |
| SQLite | ✅ | WAL, indexes, thread-local reuse, aiosqlite pool |
| Cache | ✅ | Custom `threading.Lock` TTL cache; sub-µs hits; thread-safe |
| NumPy | ✅ | Vectorized indicators incl. new ADX/BBANDS/CCI/Hurst |
| Latency evidence | ❌ | No live ANALYZE round-trip measurements on disk (carried) |

## 11. Security Audit

| Check | Status | Evidence (this pass) |
|---|---|---|
| Bandit | ✅ exit 0 | re-run |
| Secrets | ✅ | `.env` untracked; validator requires key; no SecretStr logging |
| SQLi | ✅ | Parameterized only |
| Telegram | ✅ | Admin allow-list; `/kill` `/resume` gated; html.escape |
| TLS | ✅ | httpx default verify |
| Idempotency | ✅ client-side | UUID v4 keys + DB dup guard; broker honoring UNCONFIRMED (documented, `openalgo.py:23-31`) — carried disclosure |
| Kill switch | ✅ | All order paths + orchestrator loop; audited blocks |
| **OPS limit** | ✅ **FIXED** | Empirical: 3/10 acquires; `settings.max_ops=3` wired through factories (`rate_limiter.py:36,149,180`; call sites `openalgo.py:820,897`) |
| **VIX gate** | 🔴 decorative | Never fed; 18.5 fallback biases decisions (F7-H-02) — security-adjacent: a risk-off control that cannot detect risk-off |
| pip-audit | 🟡 unverifiable | Not installed in venv |

**Verdict:** Classic security posture clean. The OPS self-limit — the CMP's loudest non-negotiable — is finally, empirically enforced. Remaining exposure is decision-integrity (VIX decorative, modification counters volatile), not perimeter.

## 12. Scalability Review

Single-process by design (LITE) — horizontal scaling out of CMP scope. Event loop non-blocking ✅ (parallel window + `to_thread`). aiosqlite pool lifecycle fixed; additions module at 71% (up from 31%). Cache thread-safe (`threading.Lock`) — R5-F-04 fully closed. New concern: the decision queue (`trade_decision_engine.decision_queue`) is unbounded and its processor task is created lazily on first enqueue (`trade_decision.py:327-331`) — if enqueues ever outpace the simulated 0.1 s routing, memory grows without bound. Bounded queue or backpressure recommended once routing is real. Low likelihood today (chain is dead — F7-C-02).

## 13. Reliability Review

Kill switch ✅ (orders + orchestrator, audited). Circuit breakers ✅ all paths (no-retry POSTs, retry ≤3 cancel — documented). Retry/backoff/jitter ✅. NSE holiday calendar ✅ (3-year frozenset, 32 tests). Misfire handling ✅. Alert flood ✅ fixed (1/min backoff, `orchestrator.py:140-144`). Orchestrator shutdown ✅ real drain (`:833-847`). aiosqlite teardown warnings ✅ gone (1 benign warning in 1123-test run). Audit JSONL-first ✅ prod / ❌ test-bypass persists (F7-M-05). **New gaps:** VIX risk-off control inert (F7-H-02); trailing stops never managed (F7-H-04); modification counters volatile across restarts (F7-M-02); decision queue unbounded (§12).

## 14. Maintainability Review

Module organization: substantially improved surface (strategy layer with clear seams: rules/strength/sizing/trailing/decision), **but** dual signal engines (F7-M-04), empty package shells + stray `src/` layer (F7-M-06), and eager settings ×10 (F7-M-03) erode it. Documentation: `VERIFICATION_RESULTS.md` (stale) deleted; `CMP_CONFORMANCE_REPORT.md` at root claims conformance this review refutes at runtime (source gate + routing stub) — doc claims again ahead of reality. Commit discipline: rules exist (`CONTRIBUTING.md`, `commit_message_check.py`) and are violated by the same wave that cites them (4th review). Repo: 343 tracked files incl. 118 docs/reports — navigability debt (F7-M-08).

## 15. Code Quality Review (live, HEAD `163cdf9`)

| Gate | Result |
|---|---|
| deps-sync | ✅ PASS |
| ruff check | ✅ PASS (0 errors; note 20-rule ignore list — F7-L-01) |
| ruff format --check | ✅ PASS (132 files) |
| isort --check-only | ✅ PASS |
| flake8 (`.flake8`) | ✅ PASS |
| **mypy `src/ --strict`** | 🔴 **FAIL — exit 2, module collision (`src/__init__.py`), checking aborted** |
| bandit | ✅ PASS |
| pip-audit | 🟡 NOT RUNNABLE (absent from venv) |
| pytest | ✅ 1123/0 … but 🔴 **coverage 76.36% < 80 → gate FAIL** |
| per-module ≥80% | 🔴 12 modules below 80 (incl. 30%, 11%, 0%) |

## 16. Testing Review

- **1123/1123 passing** — largest, greenest suite in the chain (843 → 1123). Warnings down 9 → 1.
- **But the pass is misleading as a conformance signal:** the CMP chain tests fabricate multi-source signals that production cannot produce (F7-C-02), and the heaviest new logic is the least covered (`trailing_stop` 11%, `backtest_sanity` 0%, `trade_decision` 30%, orchestrator CMP body untested). Coverage aggregate fell below the gate.
- Strong areas: circuit_breaker 99%, payload_builder 100%, logging 100%, performance_analyzer 97%, sizing 96%, rules 92%, trading_strategy/core 91%.
- Failure-path tests for the legacy stack remain good (rate-limit regression incl. OPS-cap integration test, CB-open, kill-switch, idempotency, NSE holidays ×32, html-escaping).
- No end-to-end test drives real orchestrator signal production → decision creation (would have caught F7-C-02).
- Audit dual-write still bypassed under pytest (F7-M-05) — the JSONL-first guarantee remains untested.

## 17. DevOps Review

CI (`ci.yml`): fail-fast; deps-sync→ruff→format→isort→flake8→mypy `--strict`→bandit→pip-audit→gitleaks→pytest `--cov-fail-under=80` + per-module; docker build on PRs; final-status. **At HEAD: mypy and coverage jobs RED (F7-C-01).** Branch protection on `main`: still absent — direct pushes bypass everything; this is the enabling condition for the 4-review misleading-commit pattern. Docker: multi-stage, `pip install --no-deps .`, non-root `USER loats`, no dev extras ✅ (F6-M-07 closed). Runtime compose CMD `-m loats.main` ✅ (carried). Metrics :8001 exposed + started ✅. Health checks present. Secrets hygiene ✅.

---

## 18. Risk Matrix

| Finding | Severity | Likelihood | Impact | Risk |
|---|---|---|---|---|
| F7-C-01 gates red at HEAD + false claims (4th review) | Critical | Certain | High (process) | 🔴 Critical |
| F7-C-02 CMP chain dead at runtime (source gate) | Critical | Certain | High (mandate no-op) | 🔴 Critical |
| F7-H-01 Analyzer routing simulated | High | Certain | High (P5 unmet) | 🟠 High |
| F7-H-02 VIX never wired; biased 18.5 default | High | Certain | Medium-High (BUY structurally blocked; risk-off inert) | 🟠 High |
| F7-H-03 new financial modules untested; cov 76.36% | High | Certain | High | 🟠 High |
| F7-H-04 trailing ratchet never driven | High | Certain | Medium (Rule 12) | 🟠 High |
| F7-M-01 BUY IV-rank 60 vs CMP 30 | Medium | Certain | Medium | 🟡 Medium |
| F7-M-02 mod-limit 30 vs 25; volatile fail-open counters | Medium | Certain | Medium | 🟡 Medium |
| F7-M-03 eager settings ×10 | Medium | Certain | Low-Med | 🟡 Medium |
| F7-M-04 dual signal engines | Medium | Certain | Low-Med | 🟡 Medium |
| F7-M-05 audit test-bypass persists despite claim | Medium | Certain | Medium | 🟡 Medium |
| F7-M-06 src/ stray layer + empty shells | Medium | Certain | Low-Med | 🟡 Medium |
| F7-M-07 options.py 90%→66% | Medium | Certain | Medium | 🟡 Medium |
| F7-M-08 repo 343 files | Medium | Certain | Low | 🟡 Medium |
| F7-L-01…07 | Low | — | Low | 🟢 Low |

## 19. Technical Debt Assessment (ranked)

1. 🔴 **F7-C-02** — source tagging + a real third producer; without it the strategy layer is ornamental.
2. 🔴 **F7-C-01** — delete `src/__init__.py`/strays; lift new-module coverage ≥80; enforce CI on `main`.
3. 🟠 **F7-H-01** — real Analyzer routing + decision persistence (audit-grade).
4. 🟠 **F7-H-02** — VIX feed + symmetric fail-safe.
5. 🟠 **F7-H-04** — trailing-stop runtime driver (Rule 12 operational).
6. 🟠 **F7-H-03 / F7-M-07** — tests for sizing/trailing/VaR/routing; options.py recovery.
7. 🟡 **F7-M-01/02** — thresholds to CMP values; counters persisted, fail-closed.
8. 🟡 **F7-M-03/04/05/06/08** — lazy settings, single signal engine, audit dual-write tested, src/ layer cleaned, repo pruned.
9. 🟢 Carried: vollib successor plan, `ta` dep drop-or-adopt, per-module gate exit verification, P1/P5 latency/forward-test evidence, ruff ignore shrink, bounded decision queue.

## 20. Production Readiness Assessment

**Verdict: NOT READY for live capital. ANALYZE-mode demo only — and current HEAD fails its own CI (mypy + coverage).**

| Gate | Status |
|---|---|
| Import / boot | ✅ (env required at import for 10 modules — F7-M-03) |
| Tests green | ✅ 1123/1123 |
| Coverage ≥80% aggregate | 🔴 **FAIL — 76.36%** |
| Coverage ≥80% per module | 🔴 12 modules below (incl. 0%, 11%, 30%) |
| Ruff / format / isort / flake8 | ✅ ✅ ✅ ✅ |
| Mypy `--strict` | 🔴 **FAIL (collision, aborted)** |
| Bandit / deps-sync | ✅ ✅ |
| pip-audit | 🟡 unverifiable (absent from venv) |
| **Order-path OPS ≤ self-limit 3** | ✅ **PASS (empirical: 3/10)** — first review in the chain to say so |
| Kill switch wired + audited | ✅ |
| Idempotency keys | ✅ client-side (broker honoring unconfirmed — carried) |
| Circuit breakers all paths | ✅ |
| Holiday calendar / IST | ✅ |
| VIX risk-off control | 🔴 inert (F7-H-02) |
| Trailing stops operational | 🔴 never driven (F7-H-04) |
| Strategy engine per CMP (runtime) | 🔴 **dead (F7-C-02)** |
| TradeDecision → Analyzer routing | 🔴 simulated (F7-H-01) |
| Docker runtime / non-root / metrics | ✅ |

**Minimum hard requirements before any live deployment:** F7-C-01 → F7-C-02 → F7-H-02 → F7-H-01 → F7-H-04 → F7-H-03 → F7-M-01/02 (CMP-correct thresholds + persistent counters) → F7-M-05.

## 21. Prioritized Improvement Roadmap (REVIEW ONLY — awaits USER APPROVAL)

**P0 — restore truthful gates + a living strategy chain (≈2 days)**
1. **F7-C-01:** delete `src/__init__.py`; relocate `src/*.py` strays (scripts/tests); re-run mypy; raise coverage on trailing_stop/trade_decision/backtest_sanity/orchestrator-CMP-body/options; install dev extras fully and re-run pip-audit; **enable branch protection requiring CI on `main`**; enforce commit-message hook.
2. **F7-C-02:** tag signal producers with real source identities; implement a third real producer; end-to-end test from real orchestrator signals through `create_trade_decision`; elevate the insufficient-signals debug log.

**P1 — make the CMP chain real (≈1 week)**
3. **F7-H-02:** wire India VIX (external feed via cached quote) into `set_vix_level`; symmetric fail-safe default.
4. **F7-H-01:** implement actual Analyzer routing through `AsyncOpenAlgoClient` (ANALYZE mode) + persist TradeDecisions and routing results to the audit trail; integration test asserting an external side-effect.
5. **F7-H-04:** trailing-stop runtime driver (per open position: price → ratchet update → Rule-7-gated SL-M modification in ANALYZE mode).
6. **F7-H-03:** ≥80% per module on the strategy layer; ratchet monotonicity property tests; sizing/VaR edge cases; options.py recovery to ≥85%.

**P2 — CMP-correct values + robustness (≈2-3 days)**
7. **F7-M-01:** BUY IV-rank `< 30` per CMP. **F7-M-02:** `max_modifications=25`, wire setting into the gate, persist counters, fail-closed.
8. **F7-M-03:** lazy settings across the 10 modules. **F7-M-04:** retire or repurpose the legacy combiner as tagged producers. **F7-M-05:** tmp-path audit files; delete the `PYTEST_CURRENT_TEST` bypass. **F7-M-06/08:** clean `src/` layer, delete empty shells, prune docs/reports tracking.

**P3 — hygiene**
9. F7-L-01…07: shrink ruff ignores; drop-or-adopt `ta`; remove dead strength-source weights; verify per-module gate exit codes; collect P1/P5 latency + forward-test evidence; bound the decision queue; vollib successor plan (carried).

---

## Appendix A — CMP (LOATS-CMP-13July2026) Conformance Matrix

### A.1 Zero-Assumption Rules (CMP §3 — NON-NEGOTIABLE)

| # | Rule | Evidence (this pass) | Verdict |
|---|---|---|---|
| 1 | NIFTY lot size 25 | `settings.py:77` nifty_lot_size=25 | ✅ |
| 2 | No 500ms resting time | No resting logic | ✅ (N/A) |
| 3 | Algo ID tagging broker's job; strategy field audit-only | No tag synthesis | ✅ |
| 4 | OPS threshold 10; self-limit ≤3 | **Empirical: singleton True, max_ops=3, 3/10 acquires**; factories default from settings; call sites bare | ✅ **CONFORMANT (F6-C-01 closed)** |
| 5 | Paper = Analyzer Mode | `openalgo_mode="ANALYZE"` default | ✅ |
| 6 | Bot-logic trailing SL + SL-M | SL-M ✅; trailing engine exists but **never driven at runtime** (F7-H-04) | 🟠 Partial |
| 7 | Modification limit 25/order | Gate enforces hard-coded 25 ✅; **settings says 30 mislabeled as Rule 7**; counters volatile, fail-open | 🟠 Partial + misconfig |
| 8 | `as_of_date` explicit; never `date.today()` | 0 × `date.today(` ✅; `as_of_date` convention still absent | 🟡 Half |
| 9 | py_vollib; newspaper4k; VADER ±0.05 | vollib (documented successor) + newspaper4k + 0.05 | 🟡 Documented deviation |
| 10 | India VIX external input only | Setter exists, **zero callers**; gate runs on 18.5 fallback (F7-H-02) | 🔴 **Violated in effect** |
| 11 | Position limits 5 NIFTY / 3 BANKNIFTY | `max_nifty_positions=5`, `max_banknifty_positions=3` + `check_position_limits` in decision path | ✅ Fixed |
| 12 | Trailing = monotonic ratchet; SL-M | Ratchet math exists (11% covered); **no runtime driver** | 🟠 Partial |

### A.2 Phases (CMP §5)

| Phase | CMP gate | Verdict |
|---|---|---|
| P0 Scaffolding (3d) | gates clean | 🟠 Was green at FR5-era; **red again at HEAD (F7-C-01)** |
| P1 Data layer (1wk) | live ANALYZE round trip | 🟠 Client ✅; round-trip latency still unevidenced |
| P2 TA/VA + Strength (1.5wk) | 9/21/50/200, BBANDS 20, CCI 20, Hurst+ADX regime, composite strength | ✅ **Implemented** (ta.py:385,414,447,546; strength package) — composite starved at runtime (A.3) |
| P3 Sentiment Lite (1wk) | scores ∈ [-1,+1] | ✅ |
| P4 Strategy + Risk (2wk) | rules, strike, 2% sizing, trailing ratchet, VaR, kill switch, backtest sanity | 🟠 ~70% — all modules exist; BUY IV threshold wrong (F7-M-01); trailing undriven; `backtest_sanity` 0% + no caller; VaR ✅ |
| P5 Orchestrator + Analyzer (1wk) | 3 gates, per-source breakers, session lifecycle, ALL decisions → Analyzer, 2-wk forward test | 🟠 ~50% — gates ✅; session ✅; **source gate unsatisfiable (F7-C-02); routing simulated (F7-H-01); per-source breakers ❌ (global only); forward test not begun** |

### A.3 SEBI card & verification (CMP §6/§7)

Audit 7-yr ✅ (2555 d); SHA-256 append-only ✅; JSONL-first ✅ prod / ❌ test-bypass (F7-M-05). Verification gates: superset configured — **mypy + coverage RED at HEAD; pip-audit unverifiable**. Latency gates instrumented / live-validated ❌.

### A.4 Structure & hygiene (CMP §4/§8)

Flat package + empty CMP-named shells; stray `src/` layer breaks mypy. Secrets ✅. Compact-repo spirit 🟡 (root clean; 343 tracked incl. 118 docs/reports).

**Conformance bottom line: closer, but still NO — not strict.** Rule 4 finally conforms (empirical). Rules 10 and the P5 routing/source-gate requirements are violated in effect; Rule 7 carries a mislabeled 30; Rule 12's engine is dormant. The strategy core now *exists in code* — this review's contribution is showing it does not yet *execute*.

---

## Appendix B — FR6 (15Aug2026) Finding Disposition (verified live this pass)

| FR6 finding | Status at `163cdf9` | Evidence delta |
|---|---|---|
| F6-C-01 OPS cap 50 vs ≤3 | ✅ **CLOSED** | Probe: identity True; max_ops 3; 3/10 and 3/10 acquires; factories default from settings (`rate_limiter.py:36,149,180`); class ctors unchanged-correct |
| F6-C-02 gates red (ruff 135/format 20/isort 11) | 🟠 **HALF-CLOSED → F7-C-01** | ruff/format/isort/flake8 now ✅ clean; but mypy now 🔴 (new collision) and coverage 🔴 76.36% — different gates, same class of failure; misleading commits continue (4th review) |
| F6-H-03 aiosqlite tier 31% / teardown | 🟡 Mostly closed | Additions 71% (was 31%); teardown warnings gone (1 benign warning); pool lifecycle fixed; still <80% |
| F6-H-04 CMP strategy core absent | 🟠 **Half-real → F7-C-02/H-01/H-04** | Modules exist + wired; **runtime-dead (source gate)**; routing simulated; trailing undriven; backtest_sanity orphaned |
| F6-H-05 orchestrator defects ×7 | ✅ **CLOSED (7/7)** | Lazy settings `:162-165`; strong task ref `:122`; single increment `:807`; real drain `:833-847`; alert backoff 1/min `:140-144`; margin==0 guard `:576-587`; TA inside 80 ms window `:169-184` |
| F6-M-01 audit PYTEST bypass | 🔴 **NOT FIXED (claim false)** | `database.py:774` bypass present; commit `a03047e` claims it killed |
| F6-M-02 flaky `test_get_wait_time` | ✅ Closed | Not reproduced; 1123/0; clock-injection landed per commits |
| F6-M-03 advisory per-module gate | 🟡 Improved | Multiple `sys.exit(1)` paths added; final `exit(0)` at :113 needs verification (F7-L-04) |
| F6-M-04 strike cache unbounded | ✅ Closed | TTLCache bounded |
| F6-M-05 weakened lint configs | 🟡 Partial | Ignore list deduped but still 20 rules incl. F401/I001 (F7-L-01); local mypy broken differently (collision) |
| F6-M-06 repo hygiene (38 root .py + 38 .md) | 🟡 Mixed | Root clean (3 .md) ✅; but repo grew 302→343; strays moved to `src/`, `docs/audit-history/` (76 files), `reports/` (42) (F7-M-06/M-08) |
| F6-M-07 dev extras in Docker image | ✅ Closed | Multi-stage; `pip install --no-deps .`; non-root |
| F6-L-01 ambiguous unicode | ✅ Closed | ruff clean incl. RUF001-003 (no longer ignored) |
| F6-L-02 redis ghost import | ✅ Closed | Custom threading.Lock cache; no redis reference |
| F6-L-03 empty-match pytest.raises | ✅ Closed | No PytestWarnings in run |
| F6-L-04 AsyncMock misuse | ✅ Closed | No RuntimeWarnings in run |
| F6-L-05 duplicate healthchecks | ✅ Closed (not re-observed) | — |
| F6-L-06 bloombergquint feed | 🟡 Carried | Feed list still unvalidated |
| F6-L-07 `ta` dep unused | 🟡 Carried | Still declared, unused |

---

## Appendix C — Verification commands (re-runnable, evidence basis of this pass)

```powershell
$py = '.\LOATS13July2026\Scripts\python.exe'

# State
git rev-parse HEAD            # 163cdf9a674a6e9c4d373d2d2481f3f47cd52cf3
git status --short            # clean

# Gates (memory: run in clean venv; flake8 reads .flake8)
& $py scripts\check_deps_sync.py                                  # PASS
& $py -m ruff check src/ tests/ scripts/ --config pyproject.toml  # PASS (0)
& $py -m ruff format --check src/ tests/ scripts/                 # PASS (132 files)
& $py -m isort --check-only src/ tests/ scripts/ --settings-path pyproject.toml  # PASS
& $py -m flake8 src/ tests/ scripts/                              # PASS
& $py -m mypy src/ --strict --config-file pyproject.toml          # FAIL exit 2 (collision)
& $py -m bandit -r src/ -c pyproject.toml -q                      # PASS
& $py -m pip-audit                                                # FAIL: module not installed
& $py -m pytest tests/ --cov=src --cov-branch --cov-fail-under=80 -q
#   → 1123 passed, 1 warning, 160.35s; coverage 76.36% → GATE FAIL (exit 1)

# F6-C-01 closure reproduction (OPS self-limit)
$env:OPENALGO_API_KEY='probe'
# probe asserts: singleton identity True; effective max_ops 3; settings.max_ops 3;
#                3/10 order acquires; 3/10 smart acquires — CONFIRMED

# F7-C-02 reproduction (dead CMP chain)
git grep -n '"source": "orchestrator"' -- src/loats/orchestrator.py   # :271 :338 :480 — all three signal types
# strength/__init__.py:384: if len(source_set) < self.min_sources (=3) → always True in production
```

## Appendix D — "Not enough evidence" disclosures

- **pip-audit gate state at HEAD:** not verifiable — the tool is declared as a dev extra but not installed in the clean venv. Stated as unverifiable, not as pass.
- **OpenAlgo server-side honoring of `Idempotency-Key`:** not verifiable from the repository (documented as unconfirmed, `openalgo.py:23-31`) — carried.
- **Live ANALYZE-mode round-trip latency (P1 gate) and the P5 2-week forward test:** no run-log evidence on disk — carried.
- **`check_per_module_coverage.py` final exit semantics** (`:113 sys.exit(0)` after warning paths): not fully traced; flagged F7-L-04 for verification rather than asserted.
- **`security.yml` weekly workflow results:** workflow present; executions not inspected.
- **Behavior of the CMP chain under real multi-source feeds:** cannot be observed — production produces one source (that IS the finding F7-C-02).

---

**End of Review #7 (Investigator). REVIEW-ONLY deliverable — no code modified. All recommendations require explicit USER APPROVAL before implementation.**

**Summary:** The 47-commit wave since FR6 delivered real substance — OPS ≤3 empirically enforced (F6-C-01 closed, first time in the chain), all seven orchestrator defects fixed, the CMP strategy layer built and wired, Rule 11 corrected, Docker hardened. But the wave also delivered its own undoing: HEAD fails mypy (a `src/__init__.py` collision) and the 80% coverage gate (76.36% — the new sizing/trailing/VaR/routing code is the least-tested in the repo); the CMP decision chain cannot execute because every signal declares `source: "orchestrator"` against a ≥3-unique-source gate; Analyzer routing is a documented simulation; the VIX gate runs on an unwired 18.5 default that structurally blocks BUY; and the commits again claim "FULLY COMPLIANT" and "READY FOR LIVE DEPLOYMENT" against a tree that fails its own CI — the fourth consecutive review to document that pattern. Two P0 packages (≈2 days) restore truthful gates and a living strategy chain. **NOT READY for live capital. ANALYZE-mode demo only.**

*Note: this report file is itself an untracked repo-root artifact — relocate to `docs/audit-history/` or remove before any release, per F7-M-08.*
