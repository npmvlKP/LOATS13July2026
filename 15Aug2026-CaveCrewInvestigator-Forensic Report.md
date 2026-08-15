# LOATS13July2026 — Forensic Engineering Report (Review #6 — CMP Conformance Audit)

**Date:** 2026-08-15
**Project:** LOATS13July2026 — Lite OpenAlgo Trading System (Indian equities/options research, OpenAlgo broker API, Telegram alerts, APScheduler + orchestrator analysis pipeline)
**Repository:** https://github.com/npmvlKP/LOATS13July2026.git (HEAD `36d0c52`, 2026-08-15 19:10 IST, working tree clean, `main` == `origin/main`)
**Python:** 3.12.7 (clean venv `G:\.OA\LOATS-13July2026\LOATS13July2026\LOATS13July2026\`)
**Master plan audited against:** `LOATS-CMP-13July2026.txt` (Compact Master Plan, "LITE" edition)
**Mode:** REVIEW ONLY — no code modified, no patches generated, no destructive operations executed. Every recommendation is conditional on explicit USER APPROVAL.

**Reviewers (Senior Engineering Review Board):** Principal Software Architect · Senior Python Engineer · Senior Code Reviewer · Production Debugging Engineer · Performance Optimization Engineer · Scalability Engineer · Security Auditor · DevOps & Infrastructure Engineer · QA / Test Architect · Reliability Engineer (SRE) · Technical Lead · Systems Design Reviewer

**Evidence basis (all live, gathered 2026-08-15 in the clean venv):**
`git log` (50+ commits since FR5 of 2026-08-08), full source read of `src/loats/` (19 modules), manifests (`pyproject.toml`, `requirements-core.txt`, `.flake8`, `.ruffignore`), CI workflows (`ci.yml`, `security.yml`), scripts (`check_deps_sync.py`, `check_per_module_coverage.py`, `check_env_settings_sync.py`, `commit_message_check.py`), Dockerfile + 3 compose files, live gate runs (deps-sync PASS, ruff FAIL 135, ruff-format FAIL 20 files, isort FAIL 11 files, flake8 PASS, mypy `--strict` PASS 27 files, bandit PASS, pip-audit PASS, pytest 843 passed / coverage 80.41%), empirical rate-limiter probe, byte-level mojibake scan, git inventory (302 tracked files).

**Baseline:** FR1 (15Jul) → FR5 (08Aug) chain; this review verifies FR5 dispositions AND — the primary objective of this pass — whether the build conforms **strictly** to `LOATS-CMP-13July2026.txt`.

---

## 1. Executive Summary

### 1.1 Verdict

**The project is NOT built strictly as per the CMP. It is a substantially conformant LITE build (~70% of plan scope) with one Critical compliance deviation and red quality gates at HEAD. NOT READY for live capital. ANALYZE-mode demo only.**

### 1.2 What the CMP demanded vs what exists

| CMP requirement | State (verified 2026-08-15) | Verdict |
|---|---|---|
| LITE: zero services, no Docker deps, pip-only | SQLite WAL + JSONL audit, in-memory TTLCache, stdlib metrics server; no Redis/Prometheus services | ✅ Conformant |
| Full pipeline: Sentiment → TA/VA → **Strength** → **Rules** → **Strike** → **Risk** → **Orchestrator** → OpenAlgo | Sentiment ✅, TA ✅ (partial indicator set), Strike ✅ (new `strike_selection.py`), Risk partial (kill switch, margin/position checks; no VaR-at-trade, no sizing engine), Orchestrator ✅ (new, wired into `main`) — **Strength composite module and Rules engine DO NOT EXIST** | 🟠 Partial |
| 6 phases, ~8–10 weeks | P0–P3 done; P4 ~40% (no rules/sizing/trailing engine/backtest); P5 ~50% (orchestrator runs, but **no TradeDecision → Analyzer routing**, no session lifecycle, no per-source breakers) | 🟠 Partial |
| **Zero-Assumption Rule 4: OPS threshold 10, self-limit ≤3 OPS** | `Settings.max_ops = 3` exists but is **NEVER WIRED**; order-path limiter default hard-codes **`max_ops=50`**; empirical probe: 50/100 acquires pass in 1s window | 🔴 **VIOLATED** |
| Audit: SHA-256 chain, append-only, 7-yr retention | Canonical SHA-256 + JSONL-first dual-write; `retention_days=2555` | ✅ Conformant (test-mode caveat: §8) |
| Verification every PR: ruff, mypy --strict, bandit, pytest cov ≥80%, pip-audit | All present in CI **plus** isort/flake8/deps-sync/per-module-coverage/gitleaks — but **ruff (135 errors), ruff-format (20 files), isort (11 files) FAIL at HEAD today** | 🔴 Gates red at HEAD |
| Latency gates: strike <5ms, cycle <100ms | Now measurable: orchestrator budgets + 4ms strike timeout implemented | ✅ Implemented (unvalidated against live data) |

### 1.3 Scorecard across the six reviews

| Dimension | FR4 (01Aug) | FR5 (08Aug) | **FR6 (15Aug, this)** | Trend |
|---|---|---|---|---|
| Tests | 325 pass / 14 fail | 640 pass / 0 fail | **843 pass / 0 fail** (+1 flaky observed) | ✅ Up |
| Coverage (aggregate) | 79.17% | 80.10% | **80.41%** | ✅ Gate met |
| Ruff | 28 errors | 0 | **135 errors (112 in `src/`)** | 🔴 **REGRESSED** |
| Ruff format / isort | (not gates) | clean | **20 files / 11 files dirty** | 🔴 **REGRESSED** |
| Mypy `--strict` | 27 errors | 0 | **0 (27 files)** | ✅ Held |
| Bandit / pip-audit | clean | clean | **clean / clean** | ✅ Held |
| Deps manifest sync | broken | broken (R5-F-22) | **synced + CI gate** | ✅ Fixed |
| Order-path rate limit | broken (R5-F-01) | broken (per-call) | **mechanically fixed — but at 50 OPS, not ≤3** | 🟠 Half-fixed |
| LITE mandate | violated | restored | **restored** (stray optional `redis` import remains) | ✅ Held |
| Repo hygiene | poor | poor | **worse** — 38 root `.py` + 20+ root `.md` artifacts tracked | 🔴 Worse |

### 1.4 The three things that matter most

1. **F6-C-01 (Critical, compliance):** the order-path rate limiter now works as a singleton — but its process-wide default is **hard-coded `max_ops=50`** while `Settings.max_ops=3` (the CMP-mandated self-limit; NSE INVG/67858 threshold is 10 OPS) is dead configuration. Verified empirically: 50 of 100 rapid acquires succeed.
2. **F6-H-02 (High, process):** HEAD `36d0c52` **fails three of its own CI gates** (ruff check, ruff format, isort) in the clean venv, while commit messages continue to claim readiness ("READY FOR PRODUCTION", "A+", "No regressions"). The misleading-commit pathology first flagged in R5b-F-NEW-1 persists.
3. **F6-H-04 (High, scope):** the CMP's strategy core — `rules.py` (IV-rank/ADX/VIX gates), `strength.py` (≥3-source composite), 2% fixed-fractional sizing, trailing-ratchet SL-M engine, session lifecycle, TradeDecision→Analyzer routing — is **absent**. What exists is a competent data/TA/sentiment/orchestration scaffold, not the CMP trading strategy.

---

## 2. Architecture Overview

```
src/loats/                              # importable package (hatch wheel target)
├── __init__.py                         # PEP 562 lazy settings; initialize_system()
├── initialization.py / loats_logging.py# logging bootstrap; structlog-first
├── metrics.py                          # stdlib ThreadingHTTPServer :8001 + in-memory stats
├── config/                             # lazy Settings (lru_cache); __all__=[Settings, get_settings]
├── models.py                           # Pydantic v2; uuid4 IDs; SL_M enum; idempotency_key field
├── database.py                         # sqlite3 thread-local + WAL + JSONL-first audit (SHA-256 canonical)
│                                       #   + aiosqlite pool (maxsize=10) + async wrappers
├── database_async_additions.py         # NEW: monkey-patch module adding true-async aiosqlite methods
├── openalgo.py                         # sync+async clients; kill switch; CB on ALL paths; Idempotency-Key
├── alerts.py                           # Telegram v20+; admin allow-list; CB-protected; html.escape
├── scheduler.py                        # APScheduler; IST+weekday+NSE-holiday aware; shared db singleton
├── orchestrator.py                     # NEW: 100ms cycle loop; TA→(sentiment‖market)→signal→risk
├── strike_selection.py                 # NEW: <5ms strike engine (atm_straddle/delta_neutral/oi_based)
├── sentiment.py / ta.py / options.py   # VADER+RSS; RSI/MACD/ATR/Supertrend/VWAP/CMF; BS/Greeks/IV
├── main.py                             # TradingSystem lifecycle; metrics server; orchestrator start/stop
└── utils/
    ├── cache.py                        # TTLCache (asyncio.Lock); stray optional redis import
    ├── circuit_breaker.py              # CLOSED/OPEN/HALF_OPEN; _state_lock; module breakers
    ├── connection_pool.py              # NEW: aiosqlite pool wrapper
    ├── payload_builder.py              # NEW: shared order-payload builder (dedupe fix)
    ├── rate_limiter.py                 # singleton factories (async+sync), custom-key caches
    ├── resilience.py                   # circuit_breaker_retry_{sync,async} decorators
    └── retry.py                        # exp backoff + jitter
```

**Runtime lifecycle:** `TradingSystem.initialize()` → metrics server (`main.py:49`) → `db.async_initialize()` + audit verify → alerts/scheduler init → `start()` → `alerts.start()` (non-blocking poll) + `scheduler.start()` + **`start_orchestrator()` (main.py:55)** → shutdown: `stop_orchestrator()` → scheduler → alerts → `async_close_all()`.

**Architectural deltas since FR5 (all verified):**
1. **Orchestrator + strike selection added** (CMP P5/P4 scope) — wired into `main`.
2. **True-async DB tier added**: `aiosqlite` dependency; `database_async_additions.py` attaches aiosqlite implementations; async methods prefer the aiosqlite pool and fall back to `asyncio.to_thread`. Result: **three overlapping persistence mechanisms** (sqlite3 thread-local, aiosqlite pool, to_thread fallback) — powerful but weakly governed (31% coverage on the additions module; "Event loop is closed" thread exceptions during tests).
3. **Payload dedupe**: shared `utils/payload_builder.py` (was ~150 LOC duplication — L-R5-10 closed).
4. **Singleton rate limiters restored** with per-factory locks, custom-key caches, and a `_reset_singletons_for_testing()` hook.

---

## 3. Reverse Engineered Data Flow

```
                 ┌────────────────────────── TradingSystem (main.py) ──────────────────────────┐
                 │  metrics :8001   alerts (Telegram poll)   scheduler (APScheduler jobs)      │
                 └──────────────────────────────────┬─────────────────────────────────────────┘
                                                    │
                      orchestrator._run_cycle_loop (100ms budget, kill-switch gated)
                          │
          TA (seq) ──► (sentiment ‖ market-data) 80ms parallel window ──► combined signal ──► risk checks
                          │                                                            │
                          ▼                                                            ▼
   AsyncOpenAlgoClient (CB+retry on GETs; CB+kill-switch+rate-limit on order POSTs)   db.async_* (aiosqlite pool → to_thread fallback)
                          │                                                            │
                          │ Idempotency-Key (UUID v4, TTL store, cancel/modify keyed   ▼
                          │ by order_id, place keyed by payload digest)      SQLite WAL + JSONL audit (JSONL-first, canonical SHA-256)
                          ▼
                    OpenAlgo REST (127.0.0.1:5000, ANALYZE default)
```

**Async boundary:** orchestrator/scheduler/alerts tasks on one event loop; aiosqlite pool spans worker threads; legacy sqlite3 calls via `to_thread`; RSS/newspaper via `to_thread`+`gather`. No sync-DB-in-async regressions observed (FR2 F-CONC-1 stays closed).

**Order path (financial-critical):** `place_order` → `_async_check_kill_switch()` → `get_order_rate_limiter().acquire()` (**default 50/s — F6-C-01**) → CB open-check (fail-fast) → `_request(..., idempotency_key=...)` → `Idempotency-Key` header + DB duplicate-order guard (`database.py:1466-1476`). Kill-switch block writes an audit entry (L-R5-8 closed).

---

## 4. Dependency Overview

| Dependency | pyproject | requirements-core | Verdict |
|---|---|---|---|
| openalgo, httpx, pydantic, pydantic-settings, APScheduler, numpy, pandas, scipy, vaderSentiment, feedparser, newspaper4k, structlog, python-telegram-bot, python-dotenv | ✅ | ✅ | ✅ Synced |
| lxml, lxml-html-clean, cryptography, cachetools | ✅ | ✅ | ✅ R5-F-22 closed |
| **aiosqlite** | ✅ `>=0.21.0` | ✅ | ✅ NEW — LITE-compatible (pure Python) |
| ta | ✅ `>=0.11.0` | ✅ | 🟡 Declared but **unused in code** (custom `ta.py` instead) |
| vollib | ✅ `>=1.0.11` | ✅ | 🟡 CMP rule 9 says `py_vollib`; ecosystem successor is `vollib` — deliberate, documented deviation (VOLLIB_MIGRATION_PLAN.md) |
| redis | ❌ | ❌ | 🟡 Not a dependency, but `utils/cache.py:23-29` still has a guarded optional `import redis.asyncio` + unused `REDIS_AVAILABLE` — dead code, LITE-drift confusion |

`scripts/check_deps_sync.py` runs as a CI gate and **PASSES** — manifest drift is now mechanically prevented.

**pip-audit (live):** No known vulnerabilities. (Local package itself skipped — not on PyPI.)

---

## 5. Master Plan (LOATS-CMP-13July2026) Conformance Matrix

This is the primary objective of Review #6. Verdict per CMP clause, all evidence live:

### 5.1 CMP §1 — Architecture & pipeline

| CMP clause | Evidence | Verdict |
|---|---|---|
| Engine → openalgo SDK/httpx → OpenAlgo REST; never modify OpenAlgo core; adapter pattern | `openalgo.py` clients only; no OpenAlgo-core code in repo | ✅ |
| Pipeline Sentiment → TA/VA → **Strength** → **Rules** → Strike → Risk → Orchestrator | `strength.py` **absent**; `rules.py` **absent**; orchestrator combines (ta+sentiment)/2 only | 🟠 Partial — 2 of 8 stages missing |
| ANALYZE mode default; LIVE only via OpenAlgo UI | `Settings.openalgo_mode="ANALYZE"` | ✅ |

### 5.2 CMP §2 — LITE tech stack

All stack items present except: `ta` lib declared-but-unused (custom indicators instead), `py_vollib`→`vollib` (justified ecosystem successor), VaR "via numpy/scipy" — **no VaR computation found in `options.py`/`ta.py`** (only portfolio Greeks); CMP "Historical VaR for pre-trade gates" **not implemented**. 🟠 Partial.

### 5.3 CMP §3 — Zero-Assumption Rules (NON-NEGOTIABLE)

| # | Rule | Evidence | Verdict |
|---|---|---|---|
| 1 | NIFTY lot size 25 | `Settings.nifty_lot_size=25` | ✅ |
| 2 | No 500ms resting time | No resting logic exists | ✅ (N/A) |
| 3 | Algo ID tagging = broker's job; strategy field audit-only | No tag synthesis in payloads | ✅ |
| 4 | **OPS threshold 10; self-limit ≤3 OPS** | `Settings.max_ops=3` **unwired**; limiter default **50** (probe: 50/100 pass) | 🔴 **VIOLATED — Critical** |
| 5 | Paper trading = OpenAlgo Analyzer Mode | ANALYZE default | ✅ |
| 6 | Bot-logic trailing SL + SL-M (bracket disabled) | `OrderType.SL_M` exists; `trailing_stop_loss` **stored/passed through only** — no monotonic-ratchet engine | 🟠 Partial |
| 7 | Order modification limit 25/order | **No modification counter anywhere** | 🔴 Not implemented |
| 8 | `as_of_date` explicit; never `date.today()` | Zero `date.today(` matches ✅; but zero `as_of_date` usage — convention absent | 🟡 Half |
| 9 | py_vollib; newspaper4k; VADER ±0.05 | vollib (successor) + newspaper4k + `sentiment_threshold=0.05` | 🟡 Deviation documented |
| 10 | India VIX external input only | No VIX usage at all (neither derived nor external) | 🟡 N/A — unimplemented |
| 11 | Position limits 5 NIFTY / 3 BANKNIFTY self-imposed | `max_position_size=1000`, `max_position_per_symbol=1000` — **limits 200× the CMP rule** | 🔴 **VIOLATED** |
| 12 | Trailing = monotonic ratchet; SL_ORDER_TYPE="SL-M" | SL-M enum ✅; ratchet engine absent | 🟠 Partial |

### 5.4 CMP §4 — Repo structure

CMP prescribes `src/connectors/`, `src/analysis/{ta,strength}.py`, `src/strategy/{rules,strike}.py`, `src/risk/{manager,kill_switch,audit}.py`, `orchestrator.py`. Actual: flat `src/loats/` package with `utils/`. **Structure deviates**, though functional equivalents exist for strike (`strike_selection.py`), orchestrator, kill-switch (in `openalgo.py`), audit (in `database.py`). Missing entirely: `connectors/`, `strategy/rules`, `risk/manager`, `strength`. 🟠 Deviation + gaps.

### 5.5 CMP §5 — Six phases

| Phase | CMP gate | Verdict |
|---|---|---|
| P0 Scaffolding+compliance (3d) | ruff/mypy/bandit clean, tests pass | ✅ Done (gates were green at FR5; **red again today**, see F6-H-02) |
| P1 OpenAlgo data layer (1wk) | live ANALYZE round trip | ✅ Done (client+SQLite+Greeks) |
| P2 TA/VA + Strength (1.5wk) | explicit periods 9/21/50/200, **BBANDS 20, CCI 20, regime via Hurst+ADX**, composite strength, deterministic outputs | 🟠 ~60% — RSI/MACD/ATR/Supertrend/VWAP/CMF only; **grep confirms NO ADX, NO BBANDS, NO CCI, NO Hurst, NO regime, no composite-strength module** |
| P3 Sentiment Lite (1wk) | scores ∈ [-1,+1] | ✅ Done (VADER ±0.05, 4h decay per docs) |
| P4 Strategy + Risk (2wk) | rules, strike, **2% fixed-frac sizing (cost+margin aware), trailing ratchet, VaR, kill switch, backtest sanity** | 🟠 ~40% — strike ✅, kill switch ✅, margin check ✅; **no rules engine, no sizing engine, no trailing engine, no VaR, no walk-forward backtest** |
| P5 Orchestrator + Analyzer deploy (1wk) | **3 decision gates (|score|>0.6, no opposition>0.4, ≥3 sources)**, **per-source circuit breaker**, **session lifecycle PRE_OPEN→REGULAR→POST_CLOSE**, ALL TradeDecisions → Analyzer, 2-wk forward test | 🟠 ~50% — 0.6 threshold ✅; opposition/≥3-source gates ❌ (only 2 sources averaged); breakers are global not per-source ❌; session lifecycle ❌ (`is_market_open` bool only); **no TradeDecision object, no Analyzer routing** — signals only stored to DB |

### 5.6 CMP §6/§7 — SEBI card & verification

- Audit 7-yr ✅ (`retention_days=2555`); SHA-256 append-only chain ✅; JSONL-first dual-write ✅ (test-mode caveat §8).
- Verification gates: CI superset of CMP list ✅ — but **red at HEAD** (ruff/format/isort).
- Latency gates: instrumented (100ms cycle budget, 5ms strike guard, 4ms strike timeout) ✅ measurable; no live-data validation yet.

### 5.7 CMP §8 — Git hygiene

`.env` untracked ✅; secrets in `.env` only ✅; CMP never asked for artifact hoarding — **302 tracked files include 38 root-level `.py` debug/verify scaffolds and 20+ root-level report `.md`s** — direct violation of the spirit of CMP §4 "compact repo". 🔴

### 5.8 Bottom line

**Strict conformance: NO.** The build honors the LITE philosophy, the audit/compliance architecture, and the data/TA/sentiment layers, but the strategy core (Rules, Strength, sizing, trailing, VaR, session lifecycle, Analyzer routing) — the part that makes it a *trading* system per the CMP — is missing, and the one non-negotiable the CMP shouts loudest about (self-limit ≤3 OPS) is configured-but-unwired while the effective limit is 50 OPS.

---

## 6. Critical Findings

### 🔴 F6-C-01 — Order-path rate limiter enforces 50 OPS; CMP self-limit (≤3) and NSE threshold (10) unwired
- **Category:** Compliance / Financial Safety
- **Severity:** Critical · **Confidence:** Certain (empirical)
- **Evidence:**
  - `src/loats/utils/rate_limiter.py:355-386` — `get_order_rate_limiter()` with no `max_ops` returns a process-wide singleton hard-coded `max_ops=50`.
  - `src/loats/openalgo.py:799,876` — call sites pass **no argument**: `if not await get_order_rate_limiter().acquire():`
  - `src/loats/config/settings.py:82` — `max_ops: int = Field(3, "Maximum orders per second")` — zero references to `settings.max_ops` in the limiter path (grep-verified).
  - Empirical probe (2026-08-15): singleton identity True; `effective max_ops: 50`; `50/100 acquires succeeded`; `settings.max_ops: 3`.
- **Root cause:** R5-F-01 fix restored the singleton but baked the old regression-era value (50) in as the default; the CMP-mandated knob (`Settings.max_ops=3`) was never plumbed through.
- **Impact:** With the limiter active at 50 ops/sec, a runaway loop can emit 50 orders/sec — **5× the NSE/INVG/67858 registration threshold (10 OPS)** and **~17× the CMP self-limit (3)**. Consequences: broker throttling/ban, SEBI exposure, uncontrolled capital placement. The one compliance control the CMP marks non-negotiable is effectively defeated by configuration drift.
- **Risk:** Critical — compliance + capital.
- **Suggested resolution (pending approval):** wire `get_order_rate_limiter(max_ops=settings.max_ops)` (or read Settings inside the factory default), add a regression test asserting the effective cap equals `settings.max_ops`, and assert cap ≤ 10 in CI.
- **Complexity:** Low (30 min + tests). **Dependencies:** none. **Priority:** **P0**.

### 🔴 F6-C-02 — HEAD fails three of its own CI quality gates
- **Category:** Process / Quality Gates
- **Severity:** Critical (blocks merge; contradicts commit claims) · **Confidence:** Certain (live runs)
- **Evidence (clean venv, HEAD `36d0c52`):**
  - `ruff check src/ tests/ scripts/ --config pyproject.toml` → **135 errors** (101×E501, 17×RUF003, 9×RUF001, 8×RUF002). `src/` alone: **112 errors** (79 E501, 33 RUF001-003).
  - `ruff format --check` → **20 files would be reformatted** (incl. `src/loats/alerts.py`, `src/loats/openalgo.py`, `src/loats/utils/cache.py`).
  - `isort --check-only` → **11 files** incorrectly sorted (incl. `tests/conftest.py`, `scripts/commit_message_check.py`).
  - Contrast: mypy `--strict` clean (27 files), flake8 clean, bandit clean, deps-sync PASS.
  - Commit `36d0c52` (same day) claims "All 843 tests pass… thread-safe singleton behavior" with no mention of lint state; earlier commits (e.g., `002dac5`) claim "Ruff linting passed" — contradicted by today's tree.
- **Root cause:** Final pushes bypassed pre-commit/CI (no CI run on direct push to `main` before this state, or gates ignored); smart-quote/en-dash characters from AI-authored text bled into docstrings (RUF001-003) alongside long lines.
- **Impact:** CI on this HEAD is red; "green gates" claims in git history are false; the R5b-F-NEW-1 misleading-commit pathology is ongoing.
- **Suggested resolution:** `ruff check --fix`, `ruff format`, `isort`, targeted unicode cleanup, then enforce pre-commit on every commit; consider requiring CI status checks on `main`.
- **Complexity:** Low (1 h). **Priority:** **P0**.

---

## 7. High Priority Findings

### 🟠 F6-H-03 — aiosqlite tier: 31% coverage, event-loop teardown defects, ungoverned tri-modal persistence
- **Evidence:** `database_async_additions.py` 31% covered (lines 33-300+ untested — the true-async bodies); pytest emits `RuntimeError: Event loop is closed` from aiosqlite worker threads (`PytestUnhandledThreadExceptionWarning`, multiple); `database.py:1788` pool `maxsize=10`; async methods dispatch aiosqlite-pool → `to_thread` fallback, while legacy sqlite3 thread-locals still exist.
- **Impact:** The production-preferred DB path is the least-tested code in the repo; closed-loop exceptions indicate pool connections outliving test loops (and potentially runtime loops); three persistence mechanisms multiply failure modes (retention, locking, audit ordering differ per path).
- **Suggested resolution:** (a) fix pool lifecycle (close joins worker threads; `pool.close()` on shutdown), (b) raise additions-module coverage ≥80% or fold it into `database.py`, (c) document the dispatch contract. **Priority:** P1. **Complexity:** Medium (1 day).

### 🟠 F6-H-04 — CMP strategy core absent (rules/strength/sizing/trailing/VaR/session/Analyzer routing)
- **Evidence:** grep-verified absences: no `rules`/`strength` modules, no IV-rank/ADX/VIX gate logic, no position-sizing engine (no 2% fixed-fractional), no monotonic trailing ratchet, no VaR computation, no `TradeDecision`, no Analyzer routing, no session lifecycle, no per-source breakers, no order-modification counter (rule 7), `max_position_size=1000` vs CMP 5 NIFTY (rule 11).
- **Impact:** The system cannot trade the CMP strategy; orchestrator signals are 2-source averages, not 3-source gated decisions; ANALYZE-mode routing of decisions does not exist.
- **Suggested resolution:** treat as the P4/P5 backlog the CMP already defines; sequence: rules engine → strength composite → sizing → trailing → session lifecycle → TradeDecision→Analyzer. **Priority:** P1 (scope). **Complexity:** High (multi-week).

### 🟠 F6-H-05 — Orchestrator correctness defects (new module)
- **Evidence (`src/loats/orchestrator.py`):**
  1. `cycle_count` double-increment (line 94 and `_record_cycle_time` line 498) — stats inflated 2×.
  2. Module-level `settings = get_settings()` (line 27) — **eager settings at import** (the NEW-L2 anti-pattern reintroduced); importing `loats.orchestrator` without `OPENALGO_API_KEY` env crashes.
  3. `asyncio.create_task(self._run_cycle_loop())` (line 61) fire-and-forget — no strong reference held; task eligible for GC mid-flight (CPython documented hazard).
  4. `shutdown()` sets the event then `await self._shutdown_event.wait()` (line 526) — waits on an already-set flag; "wait for current cycle" is a no-op.
  5. Persistent cycle errors → `alerts.send_system_alert` every 100ms cycle — **alert spam, no backoff**.
  6. Margin ratio `utilized/available` (line 414) — `ZeroDivisionError` when `available_margin == 0` (frozen funds edge).
  7. TA analysis runs sequentially *before* the 80ms parallel window; a slow `get_history` (httpx timeout 30s) stalls the whole loop far beyond the 100ms budget.
- **Impact:** stats wrong; import fragility; task-loss risk; alert floods; divide-by-zero on a realistic broker state.
- **Suggested resolution:** fix each; add regression tests; move settings access into methods. **Priority:** P1. **Complexity:** Low-Medium (½ day).

---

## 8. Medium Priority Findings

- **🟡 F6-M-01 — Audit JSONL write is skipped under pytest** (`database.py:655-657`: `if os.environ.get("PYTEST_CURRENT_TEST"): skip`). The JSONL-first dual-write guarantee (R5-F-14 fix) is therefore **never exercised by the test suite**, and test-runtime behavior diverges from production. Suggested: use tmp-path audit files in tests instead of a prod-path bypass. P2.
- **🟡 F6-M-02 — Flaky rate-limiter test.** `tests/test_rate_limiter.py::TestAsyncRateLimiter::test_get_wait_time` FAILED in a full-suite `-x` run yet passes in isolation (28/28) — timing/window sensitivity. Flaky suite undermines gate trust. P2.
- **🟡 F6-M-03 — Per-module coverage gate is advisory only.** `check_per_module_coverage.py` prints "FAILED (warnings detected)" then `sys.exit(0)`. Below-80% modules at HEAD: `database_async_additions` 31%, `orchestrator` 57%, `rate_limiter` 72%, `strike_selection` 74%, `scheduler` 76%, `alerts` 79%. R5b-F-NEW-4 only half-closed. P2.
- **🟡 F6-M-04 — Strike-selection cache unbounded.** `StrikeSelectionEngine._cache` (dict, keyed by price/strategy) grows forever — one entry per distinct price tick. Memory leak on a long-running 100ms loop. P2.
- **🟡 F6-M-05 — Ruff config weakens the CMP gate.** `[tool.ruff.lint] ignore` list disables F401/F841/I001/B007/T201 and more (with duplicated entries E402/I001/F401/F541); `mypy` config in pyproject is *relaxed* (salvaged only by the CI `--strict` CLI flag); local bare `mypy`/`ruff` runs under-report. P2.
- **🟡 F6-M-06 — Repo hygiene regression.** 302 tracked files: 38 root-level `.py` debug/verify scaffolds, 20+ root report `.md`s, `package.json`/lock, plus untracked junk (`$null`, `[100%]`, `0.21.0`, six `pytest_final*.log`). R5-4 worsened despite "RESOLVED" commit claims. P2.
- **🟡 F6-M-07 — Docker image installs dev extras.** Dockerfile: `pip install -e ".[dev]"` — dev tooling in the production image; editable install in-container. Runtime compose volume `device: ./logs` relative bind (L-R5-12 still open). P3/P2.

---

## 9. Low Priority Findings

- **🟢 F6-L-01** — 34 RUF001/002/003 "ambiguous unicode" hits (smart quotes/en-dashes in strings/docstrings/comments). Byte-scan: **0 U+FFFD** in `src/` — cosmetic, not corruption (R5-F-21 stays refuted).
- **🟢 F6-L-02** — `utils/cache.py` optional `redis` import + unused `REDIS_AVAILABLE` — dead LITE-drift code.
- **🟢 F6-L-03** — `pytest.warns(..., match="")` empty-match in `test_orchestrator.py` (always passes).
- **🟢 F6-L-04** — `AsyncMock ... never awaited` RuntimeWarning in `test_scheduler_coverage` (mock misuse).
- **🟢 F6-L-05** — Dockerfile/`Dockerfile` HEALTHCHECK + compose duplicate healthcheck definitions (benign).
- **🟢 F6-L-06** — bloombergquint RSS feed likely defunct (carried since FR1) — sentiment source list unvalidated.
- **🟢 F6-L-07** — `ta>=0.11` declared but unused (custom `ta.py`) — either adopt or drop the dependency.

---

## 10. Performance Review

| Item | Status | Evidence |
|---|---|---|
| Cycle <100ms | Instrumented | orchestrator budgets (30/40/20/10ms) + adaptive sleep; **unvalidated live**; TA-outside-window design flaw (F6-H-05.7) |
| Strike <5ms | Instrumented | 4ms `wait_for` + 5ms warning + fallback mid-strikes; unbounded cache (F6-M-04) |
| Trail <1ms | ❌ N/A | no trailing engine exists |
| SQLite | ✅ | WAL, indexes, thread-local reuse, aiosqlite pool |
| Cache | ✅ | in-memory TTLCache, sub-µs hits; `asyncio.Lock` (not thread lock — see R5-F-04 note) |
| NumPy vectorization | ✅ | ta.py indicators vectorized; supertrend loop inherent |

## 11. Security Audit

| Check | Status |
|---|---|
| Bandit | ✅ clean |
| pip-audit | ✅ no known vulns |
| Secrets | ✅ `.env` untracked; no default API key; validator requires value; no SecretStr logging |
| SQLi | ✅ parameterized only (raw-SQL hatches removed since FR2) |
| Telegram | ✅ admin allow-list; `/kill`,`/resume` gated; html.escape applied broadly (final sweep + tests present) |
| TLS | ✅ httpx default verify |
| Idempotency | ✅ UUID v4 `Idempotency-Key` on all order methods + DB duplicate guard (OpenAlgo server-side honoring UNCONFIRMED — documented in `openalgo.py:23-31`) |
| Kill switch | ✅ wired all order paths + orchestrator loop; blocked orders audited |
| **Rate-limit safety** | 🔴 **50 OPS effective (F6-C-01)** |

**Verdict:** No classic security holes; the financial-safety exposure is the OPS cap (F6-C-01).

## 12. Scalability Review
Single-process by design (LITE) — horizontal scaling out of scope per CMP. Event loop non-blocking ✅. aiosqlite pool + connection registry improve vertical headroom; tri-modal persistence needs governance (F6-H-03). Cache concurrency: `asyncio.Lock` adequate for single-loop today; **not thread-safe** if `to_thread` callers ever touch it (FR5's threading.Lock recommendation not implemented as such — commit claim "thread-safe TTLCache" overstated).

## 13. Reliability Review
Kill switch ✅ (orders + orchestrator). Circuit breakers ✅ all paths, no-retry on POSTs, retry≤3 on cancel (documented). Retry+backoff+jitter ✅. NSE holiday calendar ✅ (3-year frozenset + 32 tests). Misfire handling ✅. Audit JSONL-first ✅ prod / ❌ test-bypass (F6-M-01). Graceful shutdown ✅ main; orchestrator shutdown no-op wait (F6-H-05.4); aiosqlite loop-closed exceptions (F6-H-03).

## 14. Maintainability Review
Module organization good; payload_builder dedupe closed L-R5-10. Weakened local ruff/mypy configs mislead developers (F6-M-05). Commit-message discipline rules exist (CONTRIBUTING.md + `commit_message_check.py`) and are **routinely violated** by the same commits that added them. Documentation regenerated (README/VERIFICATION/RUNBOOK/DEPLOY) — some claims again ahead of reality.

## 15. Code Quality Review (live, HEAD)

| Gate | Result |
|---|---|
| deps-sync | ✅ PASS |
| ruff check | 🔴 **135 errors** |
| ruff format | 🔴 **20 files** |
| isort | 🔴 **11 files** |
| flake8 (`.flake8`) | ✅ PASS |
| mypy `--strict` | ✅ PASS (27 files) |
| bandit | ✅ PASS |
| pip-audit | ✅ PASS |
| pytest 843/843 | ✅ (1 flaky observed) |
| coverage | ✅ 80.41% aggregate; 🔴 6 modules <80% (advisory gate) |

## 16. Testing Review
843 tests / 56 files; strong areas: circuit_breaker 99%, payload_builder 100%, loats_logging 100%, models 94%. Weak: aiosqlite additions 31%, orchestrator 57% (the two **newest core modules**), rate_limiter 72%. Failure-path tests improved (rate-limit regression, CB-open, kill-switch, idempotency). Flaky `test_get_wait_time` (F6-M-02). `tests/scratch/` quarantine exists (L-R5-1 partially done) yet 38 root-level `.py` scaffolds remain tracked.

## 17. DevOps Review
CI (ci.yml): fail-fast matrix; deps-sync→ruff→format→isort→flake8→mypy --strict→bandit→pip-audit→gitleaks; pytest+cov 80 + per-module (advisory); docker build on PRs; final-status job. security.yml weekly (gitleaks/pip-audit/bandit/safety/SBOM). Docker: non-root ✅, read-only FS ✅, no-new-privileges ✅, resource caps ✅, runtime compose with `command: ["python","-m","loats.main"]` ✅ (R5-8 closed), metrics 8001 exposed & started ✅ (R5-2 closed). Gaps: dev-extras in image (F6-M-07), relative bind mounts (L-R5-12), **HEAD would fail CI** (F6-C-02).

---

## 18. Risk Matrix

| Finding | Severity | Likelihood | Impact | Risk |
|---|---|---|---|---|
| F6-C-01 OPS cap 50 vs ≤3/≤10 | Critical | Certain | Critical (SEBI/capital) | 🔴 Critical |
| F6-C-02 gates red at HEAD + false commit claims | Critical | Certain | High (process) | 🔴 Critical |
| F6-H-03 aiosqlite tier untested/teardown | High | Medium | High | 🟠 High |
| F6-H-04 CMP strategy core absent | High | Certain | Medium (scope) | 🟠 High |
| F6-H-05 orchestrator defects (7) | High | Medium | Medium | 🟠 High |
| F6-M-01 audit test-bypass | Medium | Certain | Medium | 🟡 Medium |
| F6-M-02 flaky test | Medium | Medium | Low | 🟡 Medium |
| F6-M-03 advisory per-module gate | Medium | Certain | Medium | 🟡 Medium |
| F6-M-04 strike cache leak | Medium | Certain | Low-Med | 🟡 Medium |
| F6-M-06 repo hygiene | Medium | Certain | Low | 🟡 Medium |
| F6-L-01..07 | Low | — | Low | 🟢 Low |

---

## 19. Technical Debt Assessment (ranked)

1. 🔴 F6-C-01 — unwired `max_ops` (the CMP's loudest non-negotiable).
2. 🔴 F6-C-02 — lint/format/isort debt across `src/` + tests (135/20/11).
3. 🟠 F6-H-04 — missing strategy core (rules/strength/sizing/trailing/VaR/session/Analyzer) — the bulk of CMP P4/P5.
4. 🟠 F6-H-03 — tri-modal persistence + 31%-covered aiosqlite tier.
5. 🟠 F6-H-05 — orchestrator correctness cluster.
6. 🟡 F6-M-01/02/03/04 — audit test-bypass, flaky test, advisory gate, cache leak.
7. 🟡 F6-M-05/06/07 — weakened local configs, repo artifact sprawl, image bloat.
8. 🟢 Carried: vollib successor plan, bloombergquint feed, `ta` dep unused, redis ghost import.

---

## 20. Production Readiness Assessment

**Verdict: NOT READY for live capital. ANALYZE-mode demo only — and current HEAD does not pass its own CI.**

| Gate | Status |
|---|---|
| Import / boot | ✅ (orchestrator import requires env — F6-H-05.2) |
| Tests green | ✅ 843/843 (1 flaky) |
| Coverage ≥80% aggregate | ✅ 80.41% |
| Coverage ≥80% per module | 🔴 6 modules below (advisory) |
| Ruff / format / isort | 🔴 🔴 🔴 **FAIL at HEAD** |
| Mypy --strict / bandit / pip-audit | ✅ ✅ ✅ |
| Deps manifests synced | ✅ |
| Kill switch wired + audited | ✅ |
| Idempotency keys | ✅ (broker honoring unconfirmed) |
| Circuit breakers all paths | ✅ |
| **Order-path OPS ≤ self-limit 3** | 🔴 **FAIL — effective 50 (F6-C-01)** |
| Holiday calendar / IST hours | ✅ |
| Strategy engine per CMP | 🔴 Absent |
| TradeDecision → Analyzer routing | 🔴 Absent |
| Docker runtime / non-root / metrics | ✅ |

**Minimum hard requirements before any live deployment:** F6-C-01 (P0) → F6-C-02 (P0) → F6-H-05 (P1) → F6-H-03 (P1) → CMP P4/P5 scope (F6-H-04, P1 program) → F6-M-01/02/03 hardening (P2).

---

## 21. Prioritized Improvement Roadmap (REVIEW ONLY — awaits USER APPROVAL)

**P0 — this week**
1. **F6-C-01:** plumb `settings.max_ops` into both limiter factories (order + smart-order, sync + async); add CI assertion `effective cap ≤ 10` and equality test vs `Settings.max_ops`. (~30 min)
2. **F6-C-02:** `ruff check --fix` + `ruff format` + `isort`; normalize the 34 ambiguous-unicode literals; re-run all gates to green; enable branch protection requiring CI on `main`. (~1 h)

**P1 — before any live-order path**
3. **F6-H-05:** orchestrator fixes — single increment count, lazy settings, strong task ref (store + `done` callback), real drain-wait on shutdown, alert backoff (e.g., max 1 system alert/min), guard `available_margin==0`, move TA inside the parallel budget. (~½ day)
4. **F6-H-03:** aiosqlite pool lifecycle fix + close-join threads; raise `database_async_additions` coverage ≥80% or merge into `database.py`; document dispatch precedence. (~1 day)
5. **F6-H-04 (program):** build CMP P4/P5 in order — `rules.py` gates (IV-rank>40/ADX<25/VIX>15 sell; inverse buy) → `strength.py` ≥3-source composite with opposition gate → 2% fixed-frac cost+margin-aware sizing → monotonic trailing ratchet with SL-M → per-source circuit breakers → session lifecycle (PRE_OPEN→REGULAR→POST_CLOSE) → `TradeDecision` routed to Analyzer. (multi-week)
6. CMP rule 7: per-order modification counter (≤25). CMP rule 11: position limits 5 NIFTY / 3 BANKNIFTY in Settings + orchestrator risk check.

**P2 — robustness/process**
7. **F6-M-01:** replace `PYTEST_CURRENT_TEST` audit bypass with tmp-path audit files so dual-write is tested. **F6-M-02:** de-flake `test_get_wait_time` (inject clock). **F6-M-03:** make per-module gate exit non-zero (or set per-module floors). **F6-M-04:** bound the strike cache (`TTLCache(maxsize=…)`).
8. **F6-M-05:** shrink ruff ignore-list; align local mypy config with CI `--strict`. **F6-M-06:** `git rm` the 38 root `.py` + 20+ `.md` artifacts; extend `.gitignore`. **F6-M-07:** slim Dockerfile to runtime deps only (`pip install .`), absolute/`env_var` bind mounts.

**P3 — hygiene**
9. F6-L-01…07: drop unused `ta` dep or adopt it; remove redis ghost import; fix empty-match pytest.warns; validate RSS feed list; carried vollib plan.

---

## Appendix A — FR5 Finding Disposition (verified 2026-08-15)

| FR5 finding | Status today | Evidence |
|---|---|---|
| R5-F-01 rate limiter per-call | ✅ Fixed mechanically (singleton + locks + reset hook + regression tests) — **but value wrong (50) → F6-C-01** | probe: identity True, 50/100 |
| R5-F-02 scheduler separate DB | ✅ Fixed | `scheduler.py:14,132` shared singleton |
| R5-F-04 TTLCache thread-safety | 🟡 Partial | `asyncio.Lock` only (event-loop scope), not `threading.Lock` |
| R5-F-06 orders bypass CB | ✅ Fixed | CB fail-fast on all 4 order methods ×2 clients |
| R5-F-07 no idempotency key | ✅ Fixed | UUID v4 keys, TTL store, DB dup guard |
| R5-F-08 no holiday calendar | ✅ Fixed | `NSE_HOLIDAYS` frozenset (3-yr) + 32 tests |
| R5-F-14 audit write order | ✅ Fixed prod / 🟡 test-bypass (F6-M-01) | `database.py:578-682` |
| R5-F-22 deps unsynced | ✅ Fixed | deps-sync gate PASS |
| R5-2 metrics never started | ✅ Fixed | `main.py:49` |
| R5-8 Docker CMD never runs app | ✅ Fixed | `docker-compose.runtime.yml` CMD `-m loats.main` |
| R5-3 CB stats race | ✅ Addressed | `_state_lock` discipline in `circuit_breaker.py` |
| R5-1 cache dead Redis params | ✅ Fixed (params gone) / 🟡 ghost import | `cache.py:23-29` |
| R5-5 HTML escape gaps | ✅ Fixed | final sweep + `test_html_escaping_final.py` |
| R5-6 / R5-F-19 metrics refactor | ✅ Done | metrics.py 85% |
| R5-7 unreachable excepts | ✅ Removed | commits `29cbb1c` et al. |
| R5b-F-NEW-1 misleading commits | 🔴 **Ongoing** | HEAD-day commits repeat the pattern |
| R5b-F-NEW-4 per-module coverage | 🟡 Half | advisory `sys.exit(0)` |
| R5-4 tracked artifacts | 🔴 **Worse** | 302 tracked incl. 38 root `.py` |
| L-DOC-1/2 stale docs | ✅ Regenerated | latency targets now measurable |
| L-R5-1/2 test bloat | 🟡 Partial | `tests/scratch/` + consolidation; root scaffolds remain |

## Appendix B — Verification commands (re-runnable)

```powershell
$py = '.\LOATS13July2026\Scripts\python.exe'
& $py scripts\check_deps_sync.py                      # PASS
& $py -m ruff check src/ tests/ scripts/ --config pyproject.toml   # FAIL 135
& $py -m ruff format --check src/ tests/ scripts/                  # FAIL 20 files
& $py -m isort --check-only src/ tests/ scripts/ --settings-path pyproject.toml  # FAIL 11
& $py -m flake8 src/ tests/ scripts/                   # PASS
& $py -m mypy src/ --strict --config-file pyproject.toml           # PASS (27 files)
& $py -m bandit -r src/ -c pyproject.toml -q           # PASS
& $py -m pytest tests/ --cov=src --cov-branch --cov-fail-under=80  # 843 passed, 80.41%

# F6-C-01 reproduction
$env:OPENALGO_API_KEY='probe'
& $py -c "import asyncio,sys; sys.path.insert(0,'src');
from loats.utils.rate_limiter import get_order_rate_limiter as g;
from loats.config import get_settings;
print(asyncio.run(asyncio.sleep(0)) or f'settings.max_ops={get_settings().max_ops}');
r=[asyncio.run(g().acquire()) for _ in range(100)]; print(sum(r),'/100 pass; cap=50')"
```

## Appendix C — "Not enough evidence" disclosures

- OpenAlgo server-side honoring of `Idempotency-Key`: **not verifiable from repo** (documented as unconfirmed in `openalgo.py:31`).
- Live ANALYZE-mode round-trip latency (CMP P1 gate) and the P5 "2-week forward test": **no evidence on disk** — no run logs validated.
- security.yml weekly job results: **not inspected this pass** (workflow file present; runs not verified).

---

**End of Review #6. REVIEW-ONLY deliverable — no code modified. All recommendations require explicit USER APPROVAL before implementation.**

**Summary:** The FR5 fix wave was real — rate-limiter singletons work, idempotency keys shipped, holidays landed, deps synced, Docker runtime fixed, orchestrator + strike selection now exist (CMP P4/P5 started). But the build is **not strictly per the CMP**: the OPS self-limit (≤3) is unwired while the effective cap is 50; the strategy core (rules/strength/sizing/trailing/VaR/session/Analyzer routing) is absent; and HEAD fails ruff/format/isort while commit messages claim green. Fix F6-C-01 and F6-C-02 first — 90 minutes of work removes both criticals.
