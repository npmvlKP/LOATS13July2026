# LOATS13July2026 — Forensic Engineering Audit Report (Review #5 / FR5-FINAL)

**Date:** 2026-08-08
**Reviewers:** Independent Senior Engineering Review Board (Principal Architect, Senior Python Engineer, Code Reviewer, Production Debugging Engineer, Performance Engineer, Scalability Engineer, Security Auditor, DevOps/SRE, QA Architect, Reliability Engineer, Technical Lead, Systems Design Reviewer)
**Mode:** REVIEW ONLY — no code modified, no implementations performed, no destructive operations executed
**Evidence basis:** Full source re-read (`src/loats/` 14 modules + `config/`, `utils/`), live `pytest` (640 tests, 80.10% coverage), live `ruff` (0 errors), live `mypy` (0 errors in 21 source files), live `bandit` (exit 0, 0 issues), live import probe, CI workflow inspection (`ci.yml`, `security.yml`), Dockerfile + docker-compose, `pyproject.toml` + `requirements-core.txt`, conftest, `.env.example`, git history (50+ commits since FR4).

> ⚠️ **Scope note:** This review uses prior 4 reviews (15July, 20July, 22July, 1August 2026) as baseline and verifies each finding's resolution. Every conclusion below is grounded in live evidence gathered on 2026-08-08. The LITE mandate (zero services, no Redis, no Prometheus, pure Python) is the design contract under test.

---

## 1. Executive Summary

| Dimension | FR4 (2026-08-01) State | Current State (2026-08-08) Verified | Verdict |
|---|---|---|---|
| Tests | 14 failed, 325 passed | **640 passed, 0 failed** | ✅ Resolved |
| Coverage | 79.17% (below gate) | **80.10%** (gate met) | ✅ Resolved |
| Ruff | 28 errors in tests/ | **0 errors** (clean) | ✅ Resolved |
| Mypy | 27 errors | **0 errors in 21 source files** | ✅ Resolved |
| Bandit | Clean | **Clean (exit 0)** | ✅ Stable |
| Import chain | OK | OK | ✅ Stable |
| CI/CD | Strict (no continue-on-error) | Strict (no continue-on-error) | ✅ Stable |
| Production readiness | "ANALYZE-mode demo — regressed" | **ANALYZE-mode demo — green gates, ONE new P0 correctness regression (rate limiter defeated)** | 🟠 Partial |

**Bottom line:** All four quality gates are GREEN for the first time across the five reviews (640/640 tests, 80.10% coverage, ruff/mypy/bandit clean). The major FR4 criticals are all genuinely resolved: Redis was removed and replaced with a `cachetools.TTLCache` in-memory layer (F-DEP-1 + F-ARCH-1 resolved via the LITE route); Prometheus was replaced with a stdlib in-memory metrics stub; the broken `call_async(retry_async(...))` composition was replaced with a proper `circuit_breaker_retry_async` decorator in a new `utils/resilience.py` module (F-CONC-6 resolved); the 14 failing tests now pass; and the dependency declaration is consistent between `pyproject.toml` and `requirements-core.txt`.

**However**, this review identified **one new CRITICAL regression** that did not exist in any prior review: commit `87cf065` (2026-08-07) **"Replaced module-level singletons with per-call rate limiters"** — this is precisely the F-CONC-3 defect from Review #2, re-introduced under a misreading of "shared state issues". The order-path rate limiters (`get_order_rate_limiter`, `get_smart_order_rate_limiter`) now create a **fresh** `AsyncRateLimiter` on every call, with an empty timestamps deque, so `acquire()` always returns `True` and the rate cap is never enforced. The regression is **baked into the test suite** (`tests/test_rate_limiter.py:267-276` and `tests/test_rate_limiter_additional.py:307-315` actively assert that two calls return *different* instances). For an order-placement path this is a SEBI-relevant safety defect. **The system is NOT production-ready in its current state.**

---

## 2. Architecture Overview

```
src/loats/                         # Real package (importable as src.loats)
├── __init__.py                    # Package init; lazy settings via __getattr__; calls initialize_system()
├── initialization.py              # Logging bootstrap (test-mode aware)
├── loats_logging.py               # structlog + stdlib dictConfig (structlog configured FIRST)
├── metrics.py                     # REWRITTEN: stdlib in-memory metrics stub (no prometheus_client)
├── config/
│   ├── __init__.py                # Lazy `settings` via PEP 562 __getattr__
│   └── settings.py                # Pydantic-settings (single source of truth; lru_cache lazy)
├── models.py                      # Pydantic v2 domain models (uuid IDs, enum-safe PnL)
├── database.py                    # SQLite (WAL) + JSONL audit; thread-local conns; async wrappers; canonical hash
├── openalgo.py                    # Sync + async OpenAlgo clients; kill switch wired; rate-limited order paths (BROKEN)
├── alerts.py                      # Telegram bot (v20+ lifecycle); admin allow-list; resilience decorator
├── scheduler.py                   # APScheduler (TA, sentiment, signal, cleanup); IST-aware; resilience decorator
├── sentiment.py                   # VADER + RSS/newspaper4k (async via asyncio.to_thread + gather)
├── ta.py                          # Vectorized RSI/MACD/ATR/Supertrend/VWAP/CMF (NumPy)
├── options.py                     # Black-Scholes, Greeks, IV (brentq+newton); ExpiredContractError
├── main.py                        # TradingSystem lifecycle; Windows signal handler; async_close_all
└── utils/
    ├── cache.py                   # REWRITTEN: cachetools.TTLCache in-memory (no redis)
    ├── circuit_breaker.py         # CLOSED/OPEN/HALF_OPEN state machine (thread-safe)
    ├── rate_limiter.py            # Sliding-window; per-call factories (REGRESSION)
    ├── retry.py                   # Exponential backoff + jitter (sync + async)
    └── resilience.py              # NEW: composed circuit_breaker_retry_{sync,async} decorator
```

**Runtime lifecycle:** `main.TradingSystem.initialize()` → `initialize_cache()` + `db.async_initialize()` + audit verification + `alerts.initialize()` + `scheduler.initialize()` → `start()` → `alerts.start()` (non-blocking polling task) + `scheduler.start()` (initial scans) → wait on shutdown event → graceful `scheduler.shutdown()` + `alerts.shutdown()` + `close_cache()` + `db.async_close_all()`.

**Architectural shift since FR4:**
1. Redis dependency **removed** — `utils/cache.py` rewritten as `cachetools.TTLCache` wrapper. Module-level `cache_manager` singleton preserved. The LITE mandate is now honored.
2. Prometheus dependency **removed** — `metrics.py` rewritten with a `_MetricFactory`/`_SimpleSetter` in-memory stub that mimics the Prometheus `.labels().inc()` API so call sites are unchanged. `start_http_server` is now a stdlib `ThreadingHTTPServer` serving JSON.
3. New `utils/resilience.py` provides `circuit_breaker_retry_{async,sync}` decorators that compose the breaker + retry patterns in a single, mypy-friendly wrapper. Pre-configured compositions (`openalgo_circuit_breaker_retry_async`, `telegram_circuit_breaker_retry_async`) are applied as decorators in `scheduler.py` and `alerts.py`.
4. Orphan scaffold (`src/{adapters,modules,orchestrator,risk,rules,strength,strike}.py`) **deleted**.
5. `openalgo_fixed.py` (656-line stub) **deleted**.

---

## 3. Reverse Engineered Data Flow

```
OpenAlgo REST API ──► AsyncOpenAlgoClient ──► @openalgo_circuit_breaker_retry_async
       │                                              │
       │                                              ▼
       │                                  scheduler._safe_get_* helpers
       │                                              │
       │                                              ▼
       └── rate_limiter (BROKEN — per-call instance) ◄── place_order / place_smart_order
                                                      │
                                                      ▼
                                       database.py (async wrappers via asyncio.to_thread)
                                                      │
                                       SQLite (WAL) + JSONL audit (canonical SHA-256)
                                                      │
                                       alerts.py (Telegram, resilience decorator)
                                                      │
                                       metrics.py (in-memory stubs; HTTP server never started in main)
```

**Async boundary:** Scheduler/alerts tasks are async. DB calls offloaded via `asyncio.to_thread`. RSS parsing uses `asyncio.to_thread` + `asyncio.gather`. Cache (`cachetools.TTLCache`) is sync but wrapped in async methods. Rate limiter is async-only.

**Critical composition (F-CONC-6 RESOLVED):** The previous inline `OPENALGO_CIRCUIT_BREAKER.call_async(retry_async(OPENALGO_RETRY_CONFIG)(lambda: ...))` pattern was replaced by a decorator:

```python
# utils/resilience.py:131
def circuit_breaker_retry_async(circuit_breaker, retry_config=None, on_retry=None):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            for attempt in range(1, cfg.max_attempts + 1):
                try:
                    return cast(T, await circuit_breaker.call_async(func, *args, **kwargs))
                except CircuitBreakerOpenError:
                    raise  # fail-fast, no retry
                except Exception as e:
                    ...  # retry handling
        return wrapper
    return decorator
```

This composition is type-safe (mypy clean), runtime-correct, and properly separates retry semantics from circuit-breaker state.

---

## 4. Dependency Overview

| Dependency | In `pyproject.toml [project]` | In `requirements-core.txt` | Installed | Verdict |
|---|---|---|---|---|
| `cachetools` | ✅ `>=5.3.0` (line 40) | ✅ `>=5.3.0` | ✅ | ✅ NEW (replaces redis) |
| `redis` | ❌ REMOVED | ❌ REMOVED | N/A | ✅ F-DEP-1 / F-ARCH-1 resolved |
| `prometheus-client` | ❌ REMOVED | ❌ REMOVED | N/A | ✅ F-DEP-1 / F-ARCH-1 resolved |
| `python-telegram-bot`, `httpx`, `pydantic`, `APScheduler`, `vollib`, `ta`, `numpy`, `pandas`, `scipy`, `vaderSentiment`, `feedparser`, `structlog`, `python-dotenv`, `newspaper4k` | ✅ All present | ✅ All present | ✅ | ✅ |
| `lxml`, `lxml-html-clean`, `cryptography` | (transitive) | ✅ Explicit | ✅ (transitive) | ✅ |

**External integrations:** OpenAlgo REST (quotes/history/orders), Telegram Bot API, RSS feeds (Economic Times, Moneycontrol, BloombergQuint). **No Redis, no Prometheus, no external services** — fully LITE-compliant.

**Fresh-install simulation:** `pip install ".[dev]"` (the CI command) now succeeds with no missing modules. The packaging contract is sound.

---

## 5. Module-by-Module Review

| Module | LOC | Coverage | Verdict | Key Notes |
|---|---|---|---|---|
| `config/settings.py` | 176 | 96% | ✅ Good | Lazy `lru_cache`; no default secret; `extra="ignore"`. |
| `loats_logging.py` | 116 | 100% | ✅ Good | structlog-first ordering; `use_get_message=False`. |
| `models.py` | 316 | 97% | ✅ Good | uuid4 IDs; enum/string-safe PnL; `model_validator(mode="before")`. |
| `database.py` | 1652 | 90% | ✅ Good | Async wrappers via `to_thread`; canonical hash write+verify; thread registry + `close_all`; per-conn PRAGMA tracking. |
| `openalgo.py` | 662 | 94% | 🟠 Issues | Kill switch wired; **rate limiter defeated by per-call factories (F-CONC-3-R)**; 94% coverage (up from 65% in FR4). |
| `alerts.py` | 869 | 73% | ✅ Good | v20+ lifecycle; HTML escaping applied (with minor inconsistencies — see R5-5); admin auth on /kill, /resume; `_polling_task` declared. |
| `scheduler.py` | 668 | 72% | ✅ Good | IST-aware weekday check; resilience decorator; async DB calls; 72% coverage. |
| `main.py` | 175 | 75% | ✅ Good | Windows signal handler; `async_close_all`; metrics server NOT started (R5-2). |
| `sentiment.py` | 191 | 76% | ✅ Good | `asyncio.to_thread` + `gather`; in-memory cache integration. |
| `ta.py` | 422 | 63% | 🟡 Fair | Vectorized NumPy; 63% coverage; many branches untested but algorithms clean. |
| `options.py` | 662 | 68% | ✅ Good | `ExpiredContractError`; `contract.quantity` used; portfolio greeks correct; 68% coverage. |
| `metrics.py` | 411 | 67% | 🟡 Fair | In-memory stub; HTTP server never invoked by main; dual API surface (Prometheus-stub AND direct methods). |
| `utils/cache.py` | 329 | 84% | 🟡 Fair | cachetools.TTLCache; **dead Redis config params (R5-1)**; **`get()` falsy-value bug (R5-1)**. |
| `utils/circuit_breaker.py` | 314 | 97% | ✅ Good | Thread-safe state machine; well-tested. |
| `utils/rate_limiter.py` | 370 | 84% | 🔴 Defect | **Per-call factory functions defeat rate limiting (F-CONC-3-R)**. |
| `utils/resilience.py` | 248 | 77% | ✅ Good | New module; clean decorator composition; properly type-safe. |
| `utils/retry.py` | 242 | 87% | ✅ Good | Exponential backoff + jitter; sync + async variants. |

---

## 6. Critical Findings

### 🔴 F-CONC-3-R — Order-path rate limiters create fresh instance per call (REGRESSION of FR#2 F-CONC-3)

- **Issue ID:** F-CONC-3-R
- **Category:** Correctness / Safety / SEBI Compliance
- **Severity:** Critical
- **Confidence:** Certain
- **Evidence:**
  - `src/loats/utils/rate_limiter.py:325-346` `get_order_rate_limiter`:
    ```python
    def get_order_rate_limiter(max_ops=None, window_size=1.0) -> AsyncRateLimiter:
        """... F-CONC-3: This function now creates a new instance per call instead of
        using module-level singletons. This ensures proper isolation between
        different callers and prevents shared state issues in production."""
        if max_ops is None:
            max_ops = 50
        return AsyncRateLimiter(max_ops=max_ops, window_size=window_size)
    ```
  - `src/loats/utils/rate_limiter.py:349-370` — identical pattern for `get_smart_order_rate_limiter`.
  - Call sites (every order placement):
    - `src/loats/openalgo.py:530` — `if not await get_order_rate_limiter().acquire():`
    - `src/loats/openalgo.py:580` — `if not await get_smart_order_rate_limiter().acquire():`
  - **The regression is enshrined in tests** that *assert* two consecutive calls return different instances:
    - `tests/test_rate_limiter.py:267-276` `test_rate_limiter_per_call` — `assert limiter1 is not limiter2`
    - `tests/test_rate_limiter_additional.py:307-315` `test_rate_limiter_per_call_behavior` — same assertion
  - Git commit `87cf065` (2026-08-07): *"## ✅ F-CONC-3 Rate Limiter Per-Call Implementation — COMPLETE ... Replaced module-level singletons with per-call rate limiters to eliminate shared state issues in production."*
- **Root Cause:** Misreading of the original F-CONC-3 finding (Review #2). The original defect was that `NimRateGuard` was instantiated per-call (stateless); the fix was to make it a module-level singleton (stateful). Commit `87cf065` inverted the fix, claiming "shared state issues" — but **the entire purpose of a rate limiter is shared global state** so multiple calls share a quota. Per-call instances have empty timestamp deques and trivially return `True` from `acquire()`.
- **Technical Explanation:** `AsyncRateLimiter.acquire()` (rate_limiter.py:151-176) checks `len(self.timestamps) < self.max_ops`. A fresh instance has `timestamps = deque()` (length 0), `max_ops = 50`. Therefore `0 < 50` is always True; the timestamp is appended and immediately discarded when the limiter goes out of scope. The 50-ops/sec cap is never enforced.
- **Impact:** Order-placement paths (`place_order`, `place_smart_order`) can be called without bound. A runaway loop, a misconfigured scheduler, or a Telegram command flood will spam OpenAlgo with unlimited order requests.
- **Possible Consequences:** (a) SEBI/exchange throttling or ban for excessive API calls; (b) accidental mass order placement in a bug scenario with no rate-limit safety net; (c) OpenAlgo broker-side rate-limit rejection (429) cascading into circuit-breaker OPEN; (d) compliance audit failure (the rate limit is documented as a safety control but is non-functional).
- **Risk Assessment:** Critical — a safety control that exists in code, is tested, passes the CI gate, and silently does nothing.
- **Suggested Resolution:** Restore module-level singletons:
  ```python
  _order_rate_limiter: AsyncRateLimiter | None = None
  _smart_order_rate_limiter: AsyncRateLimiter | None = None
  
  def get_order_rate_limiter(max_ops=None, window_size=1.0) -> AsyncRateLimiter:
      global _order_rate_limiter
      if _order_rate_limiter is None:
          _order_rate_limiter = AsyncRateLimiter(max_ops=max_ops or 50, window_size=window_size)
      return _order_rate_limiter
  ```
  Then **invert the regression tests** at `test_rate_limiter.py:267-276` and `test_rate_limiter_additional.py:307-315` to assert that two calls return the *same* instance. Add a concurrency test that fires 100 rapid `place_order` calls and verifies the limiter rejects calls beyond `max_ops` within the window.
- **Estimated Complexity:** Low (1 hour — code change + test inversion + new concurrency test)
- **Dependencies:** None
- **Priority:** P0

---

### 🟠 R5-1 — `utils/cache.py` carries dead Redis configuration params + `get()` falsy-value bug

- **Issue ID:** R5-1
- **Category:** Code Quality / Correctness
- **Severity:** Medium
- **Confidence:** Certain
- **Evidence:**
  - `src/loats/utils/cache.py:30-32, 48-51` — `CacheConfig.__init__` accepts `redis_host`, `redis_port`, `redis_password` and stores them as attributes, but **none are ever read** after the LITE rewrite (`initialize()` always builds a `TTLCache`).
  - `src/loats/utils/cache.py:113` — `return str(result) if result else None`. The `if result` test is falsy for any cached value of `0`, `0.0`, `""`, `False`, or empty containers. Combined with `get_or_set` at L188-194 which calls `get()` and treats `None` as a cache miss, this means a legitimately cached falsy value will be re-fetched every time (cache miss forever).
- **Root Cause:** Incomplete refactor — Redis parameters retained for "backward compatibility" but unused; truthiness test conflates "missing key" with "falsy value".
- **Impact:** Dead parameters mislead operators into thinking Redis is configurable. Falsy cached values silently defeat caching.
- **Possible Consequences:** Operator confusion; cache ineffectiveness for zero-valued numerics (common in trading — e.g., `pnl: 0.0`, `change: 0`).
- **Risk Assessment:** Medium — observability/correctness degradation.
- **Suggested Resolution:** Remove `redis_host`/`redis_port`/`redis_password` from `CacheConfig`. Replace `if result is not None` (the canonical sentinel test) instead of `if result`.
- **Estimated Complexity:** Low (30 minutes)
- **Dependencies:** None
- **Priority:** P2

---

### 🟠 R5-2 — Metrics HTTP server is never started in production

- **Issue ID:** R5-2
- **Category:** DevOps / Observability
- **Severity:** Medium
- **Confidence:** Certain
- **Evidence:**
  - `src/loats/metrics.py:290-303, 378-411` — `MetricsManager.start_server(port)` and module-level `start_metrics_server(port)` exist and start a stdlib `ThreadingHTTPServer` on port 8001.
  - `src/loats/main.py:34-47` — `TradingSystem.initialize()` calls `initialize_cache`, `db.async_initialize`, `alerts.initialize`, `scheduler.initialize`. **It does NOT call `start_metrics_server`**.
  - `docker-compose.yml:41` exposes port `8001:8001` and comments "Prometheus metrics server" — but nothing inside the container binds to 8001 in production.
  - The container's `CMD` (Dockerfile:65) is `python quick_health_check.py` — not the trading system, so even the in-process metrics dict is never populated.
- **Root Cause:** Lifecycle wiring gap — the metrics module was rewritten but never hooked into `TradingSystem.initialize()`.
- **Impact:** Operators see port 8001 open in the compose file but the endpoint is dead. The metrics summary (`get_metrics_summary()`) is collected in-process but never exposed externally. No `/metrics`-equivalent endpoint to scrape.
- **Possible Consequences:** Operators have no visibility into job execution counts, latency, or signal generation rates. Defeats the observability goal the metrics module was built for.
- **Risk Assessment:** Medium — observability gap in a system that requires operational monitoring.
- **Suggested Resolution:** In `main.TradingSystem.initialize()`, after `initialize_cache()`, add `start_metrics_server(port=settings.metrics_port)` (and add `metrics_port: int = 8001` to `Settings`). Alternatively, document explicitly that metrics are in-process only and expose them via a periodic log line.
- **Estimated Complexity:** Low (30 minutes)
- **Dependencies:** None
- **Priority:** P2

---

## 7. High Priority Findings

### 🟠 R5-3 — Circuit-breaker statistics mutated without lock (concurrent sync+async race)

- **Issue ID:** R5-3
- **Category:** Correctness / Concurrency
- **Severity:** Medium
- **Confidence:** Likely
- **Evidence:** `src/loats/utils/circuit_breaker.py:141-176` — `_record_success` and `_record_failure` mutate `self._stats` (increment counters, set `last_failure_time`, modify `_state`) **without acquiring `self._state_lock`**. The lock is only held by the `state` property (L109-117) and `get_status` (L276-294). Concurrent calls to `call()` (sync, from APScheduler worker threads) and `call_async()` (async, from event loop) can both pass the `if self.state == OPEN` check, both invoke the wrapped function, and both modify `_stats` and `_state` unlocked.
- **Root Cause:** Lock discipline incomplete — state reads are locked but state writes are not.
- **Impact:** Statistics counters can be lost (read-modify-write race on `total_calls += 1`). In rare interleavings, the breaker may OPEN late or skip a HALF_OPEN → CLOSED transition. The breaker itself never gets *stuck* (worst case is over-counting failures), but the monitoring numbers (`get_status`) will be inaccurate.
- **Risk Assessment:** Medium — monitoring accuracy defect, not a state-machine correctness defect.
- **Suggested Resolution:** Acquire `self._state_lock` inside `_record_success` and `_record_failure` when modifying `_stats` or `_state`. Use a separate `_stats_lock` if the contention cost of holding `_state_lock` during stats mutation is too high.
- **Estimated Complexity:** Low (1 hour)
- **Dependencies:** None
- **Priority:** P1

---

### 🟠 R5-4 — Tracked session artifacts pollute the repository

- **Issue ID:** R5-4
- **Category:** Hygiene / Maintainability
- **Severity:** Medium
- **Confidence:** Certain
- **Evidence:** `git ls-files` shows the following files **committed to `main`**:
  - `01August2026-Forensic-Engineering-Audit-FR4.md` (prior review report — 600+ lines)
  - `VERIFICATION_RESULTS.md` (stale claims from earlier reviews)
  - `bandit_output.json`, `bandit_output.txt`, `bandit_output_final.json`, `bandit_output_fixed.json` (four bandit output dumps)
  - `task_progress.md` (work-in-progress todo list from a prior session)
  - Working tree additionally contains untracked: `08August2026-Forensic-Engineering-Audit-FR5.md`, `08August2026-Forensic-Engineering-Audit-FR5b.md`, `qg_*.txt`
- **Root Cause:** Ad-hoc session outputs checked into the repo instead of `.gitignore`.
- **Impact:** Repo bloat; misleading audit trail (the `VERIFICATION_RESULTS.md` claims contradict live evidence); confusing for new contributors.
- **Risk Assessment:** Medium — professional repo hygiene.
- **Suggested Resolution:** Move all `*Forensic*Engineering*Audit*.md`, `bandit_output*.json`, `bandit_output.txt`, `qg_*.txt`, `task_progress.md` out of the repo (or into a `docs/audit-history/` subdirectory if retention is desired). Add `*.audit.md`, `bandit_output*.json`, `qg_*.txt`, `task_progress.md` to `.gitignore`. Regenerate `VERIFICATION_RESULTS.md` after each release with live command output.
- **Estimated Complexity:** Low (15 minutes)
- **Dependencies:** None
- **Priority:** P2

---

### 🟡 R5-5 — HTML escaping applied inconsistently across alert message builders

- **Issue ID:** R5-5
- **Category:** Security (defense-in-depth)
- **Severity:** Low
- **Confidence:** Certain
- **Evidence:** `src/loats/alerts.py` applies `html.escape()` to user/external data, but coverage is inconsistent:
  - ✅ `send_signal_alert` (L283-301): escapes indicator names, values, symbol, metadata keys/values.
  - ✅ `send_position_alert` (L456-465): escapes `symbol`, `product_type`.
  - ✅ `_orders` command (L760-765): escapes `order_id`, `symbol`, `order_type`, `transaction`, `price`, `status`.
  - ✅ `activate_kill_switch` (L545), `deactivate_kill_switch` (L570), `_kill_switch` (L674), `_resume` (L714): escape `reason`.
  - ❌ `send_order_alert` (L326-337): interpolates `order.order_id`, `order.symbol`, `order.order_type.value`, `order.transaction_type.value` **without escaping**.
  - ❌ `send_trade_alert` (L371-381): interpolates `trade.trade_id`, `trade.symbol`, `trade.strategy`, `trade.transaction_type.value` **without escaping**. `trade.strategy` is a free-text field set by the trading layer.
- **Root Cause:** Defense-in-depth escaping was added incrementally per-method as findings were filed, leaving older methods untouched.
- **Impact:** Low — these data sources are system-internal (not directly user-supplied), but `symbol` and `strategy` flow through from broker/config data. A future change that surfaces user-supplied text via these paths would inherit the unescaped behavior.
- **Risk Assessment:** Low — defense-in-depth gap, not an exploitable vulnerability today.
- **Suggested Resolution:** Apply `html.escape()` uniformly to every external-data interpolation in `send_order_alert` and `send_trade_alert`, or centralize alert formatting in a helper that escapes by default.
- **Estimated Complexity:** Low (30 minutes)
- **Dependencies:** None
- **Priority:** P3

---

## 8. Medium Priority Findings

### 🟡 R5-6 — `MetricsManager.__new__` re-sets `_initialized` only on first construction (fragile singleton)

- **Issue ID:** R5-6
- **Category:** Code Quality
- **Severity:** Low
- **Confidence:** Likely
- **Evidence:** `src/loats/metrics.py:74-78`:
  ```python
  def __new__(cls) -> "MetricsManager":
      if cls._instance is None:
          cls._instance = super().__new__(cls)
          cls._instance._initialized = False
      return cls._instance
  ```
  This pattern works today (the `_initialized = False` is inside the `if` block), but the `_initialized` attribute is set BEFORE `__init__` runs, which is unusual. `reset_for_testing()` (L174-194) sets `_initialized = False` directly to force re-initialization on next `__init__`, but `__init__` itself guards with `if getattr(self, "_initialized", False): return` — so the reset relies on a subtle interaction.
- **Risk Assessment:** Low — works today, fragile to future edits.
- **Suggested Resolution:** Use a proper `@functools.lru_cache(maxsize=1)` factory function instead of `__new__`-based singleton, or document the lifecycle contract in the class docstring.
- **Priority:** P3

---

### 🟡 R5-7 — `_safe_get_*` helpers contain unreachable `except CircuitBreakerOpenError` branches

- **Issue ID:** R5-7
- **Category:** Code Quality / Dead Code
- **Severity:** Low
- **Confidence:** Certain
- **Evidence:** `src/loats/scheduler.py:172-198, 374-396` and `src/loats/alerts.py:419-441, 495-505, 507-518`:
  ```python
  @openalgo_circuit_breaker_retry_async
  async def _safe_get_history(self, ...) -> dict[str, Any] | None:
      try:
          return await async_client.get_history(...)
      except CircuitBreakerOpenError:    # ← unreachable
          logger.warning("OpenAlgo circuit breaker open get_history")
          raise
      except Exception:
          ...
  ```
  The decorator (`circuit_breaker_retry_async` in `utils/resilience.py:160-208`) calls `circuit_breaker.call_async(func, ...)`; when the breaker is OPEN, `call_async` raises `CircuitBreakerOpenError` **before** `func` is invoked. Therefore the inner `try` body never executes when the breaker is open, and the inner `except CircuitBreakerOpenError` is unreachable for the open-breaker case. The decorator's own `except CircuitBreakerOpenError: raise` (L172) handles it.
- **Risk Assessment:** Low — confusing dead code; future maintainers may believe the inner handler is the active path.
- **Suggested Resolution:** Remove the inner `except CircuitBreakerOpenError` branches. Keep only the broad `except Exception` for non-breaker failures (which can occur inside the wrapped function).
- **Priority:** P3

---

### 🟡 R5-8 — `docker-compose.yml` healthcheck vs Dockerfile `CMD` both run `quick_health_check.py`; container never runs the trading system

- **Issue ID:** R5-8
- **Category:** DevOps / Deployment
- **Severity:** Medium
- **Confidence:** Certain
- **Evidence:**
  - `Dockerfile:65` — `CMD ["python", "quick_health_check.py"]` (container's default command).
  - `docker-compose.yml:43` — `healthcheck.test: ["CMD", "python", "quick_health_check.py"]`.
  - The actual `loats.main:cli_main` entry point (declared in `pyproject.toml:66`) is **never invoked** by either Docker config.
- **Root Cause:** The container was built for CI health-check purposes (matches the LITE "demo only" stance), but the compose file labels the container as the production `loats13july2026` service with `restart: unless-stopped`.
- **Impact:** An operator running `docker compose up` gets a container that runs a health check once and exits (or, with `restart: unless-stopped`, restarts in an infinite loop doing nothing). The trading system never starts.
- **Risk Assessment:** Medium — deployment trap.
- **Suggested Resolution:** Either (a) split into two compose files (ci-test vs runtime) and set the runtime `CMD` to `["python", "-m", "loats.main"]`; or (b) document explicitly that this compose is for CI only and add a `docker-compose.prod.yml` override with the proper CMD.
- **Priority:** P2

---

## 9. Low Priority Findings

- **L-R5-1:** Duplicate-looking test files suggest iterative patch history rather than edits: `test_openalgo.py`, `test_openalgo_comprehensive.py`, `test_openalgo_comprehensive_fixed.py`, `test_openalgo_comprehensive_fixed2.py`, `test_openalgo_integration.py`, `test_openalgo_integration_fixed.py`. Six files for the same module. Consolidate into one canonical test file per source module after verifying coverage doesn't drop.
- **L-R5-2:** `tests/debug_kill_switch.py`, `tests/test_kill_switch_fixed.py`, `tests/test_kill_switch_simple.py`, `tests/test_final_logging_verification.py`, `tests/test_logging_implementation.py` — debugging scaffolds committed under `tests/`. Move to a `tests/scratch/` dir or delete.
- **L-R5-3:** `.env.example` references `NIM_MAX_REQUESTS_PER_MINUTE`, `NIM_MIN_GAP_SECONDS`, `NIM_MAX_CONTEXT_TOKENS` — but `Settings` has no such fields (the `nim_rate_guard.py` module was deleted). With `extra="ignore"` the env vars are silently ignored. Misleading.
- **L-R5-4:** `cache.py:130-135` re-initializes the cache mid-`set()` if `_cache is None` — defensive but masks the bug of why `_cache` was None after `initialize()`. Remove or assert.
- **L-R5-5:** `metrics.py` exposes two parallel APIs: `_MetricFactory`-based Prometheus-style stubs (`job_execution_counter`, etc., used by the `track_job` decorator) AND direct methods (`track_job_execution`, `record_signal`, etc.). Only one is needed; the duplication doubles the test surface and risks drift.
- **L-R5-6:** `tests/conftest.py:35-38` `configure_test_logging` is `autouse=True` but has no yield/cleanup — fine, but the `@pytest.fixture(autouse=True)` pattern without scope means it runs per-test (acceptable, just noted).
- **L-R5-7:** `pyproject.toml:147` `disallow_any_generics = false` — inconsistent with `--strict` (which CI uses at `ci.yml:40`). Either align with strict or remove the override.
- **L-R5-8:** `options.py` still depends on `vollib>=1.0.1` (L-FUTURE-1 from FR#1, still open). `vollib` is deprecated. Open since 2026-07-15.

---

## 10. Performance Review

| ID | Finding | Severity | Status |
|---|---|---|---|
| F-PERF-1 | SQLite PRAGMAs re-run per connection | Low | ✅ Mitigated (per-instance `_pragmas_applied` set) |
| F-PERF-2 | `supertrend` Python loop | Low | 🟡 Inherent (NumPy mitigates) |
| F-PERF-3 | WAL mode, indexes, `asyncio.gather` for RSS | — | ✅ Good |
| F-PERF-4 | In-memory cache (`cachetools.TTLCache`) | — | ✅ Good (no external service) |
| F-PERF-5 | `asyncio.to_thread` offloads DB I/O | — | ✅ Good |
| R5-PERF-1 | `cache_manager.get_or_set` calls `await self.get(key)` which is async-wrapped sync dict lookup — adds event-loop overhead per cache read | Low | 🟡 Minor |
| R5-PERF-2 | `circuit_breaker_retry_async` rebinds `cfg = retry_config or RetryConfig()` on every call inside the wrapper (resilience.py:162) — wasteful but tiny | Low | 🟡 Minor |

**Latency targets:** README still claims `<5ms strike selection`, `<100ms cycle`. **No strike-selection or orchestrator module exists in the real package.** Targets remain unmeasurable (carried from FR#1 L-DOC-1).

---

## 11. Security Audit

| Check | Status | Evidence |
|---|---|---|
| Bandit | ✅ Clean (exit 0, 0 issues) | `bandit -r src/loats -c pyproject.toml` |
| `.env` gitignored | ✅ Yes | `.gitignore` |
| Hardcoded secret default | ✅ Fixed | `settings.py:54-56` — no default, validator requires non-empty |
| SQL injection | ✅ Fixed | Raw-SQL public methods removed; all SQL parameterized |
| HTML injection (Telegram) | ✅ Mostly fixed | `html.escape()` applied (R5-5 — minor inconsistencies remain) |
| Telegram auth | ✅ Fixed | `_is_authorized_admin` checks `telegram_admin_ids`; `/kill` and `/resume` gated; default-deny when list empty |
| Kill switch enforcement | ✅ Fixed | `_check_kill_switch` / `_async_check_kill_switch` in `place_order`, `place_smart_order`, `modify_order`, `cancel_order` |
| TLS verification | ✅ Default | httpx verifies TLS by default |
| Secret logging | ✅ None observed | No `SecretStr` values logged |
| Rate-limit safety on order paths | 🔴 **DEFEATED** | F-CONC-3-R (per-call limiter instances) |
| Dependency vulnerabilities | 🟡 Unknown | `pip-audit` configured in CI; not run in this review |

**Verdict:** Security posture remains substantially improved over baseline. **One new Critical safety regression** (F-CONC-3-R) offsets the kill-switch/auth/SQLi gains in the order-placement risk envelope.

---

## 12. Scalability Review

| Aspect | Status | Notes |
|---|---|---|
| Horizontal scaling | 🔴 Single-process | SQLite + APScheduler in-process; no sharding/federation |
| Event-loop blocking | ✅ Fixed | DB I/O offloaded via `asyncio.to_thread` (F-CONC-1 resolved) |
| Caching | ✅ Present and active | In-memory `TTLCache` (LITE-compliant); no external service |
| Rate limiting | 🔴 **Ineffective on order paths** | F-CONC-3-R regression |
| Circuit breakers | ✅ Functional | Composition via `resilience.py` decorator; properly type-safe |
| Async I/O | ✅ Good | `asyncio.gather` for RSS; `to_thread` for blocking ops |

---

## 13. Reliability Review

| Aspect | Status | Notes |
|---|---|---|
| Retry strategy | ✅ Functional | `retry_async` + `circuit_breaker_retry_async` decorator; properly composes with breaker |
| Timeout handling | ✅ Good | `settings.request_timeout`; httpx timeouts |
| Circuit breaker | ✅ Functional | Properly type-safe; HALF_OPEN transition; thread-safe state reads (R5-3 — stats race) |
| Graceful degradation | ✅ Good | Cache disabled silently on init failure; circuit breaker returns `None` on open via per-caller catch |
| Fail-safe kill switch | ✅ Fixed | Wired into all order paths |
| Audit integrity | ✅ Fixed | Canonical serialization on write AND verify paths (F-DATA-1 + F-DATA-2 fully resolved) |
| DB cleanup on shutdown | ✅ Fixed | `async_close_all()` closes all thread-local connections via thread registry |
| Misfire handling | ✅ Good | `misfire_grace_time=30`, `coalesce=True`, `max_instances=1` |

---

## 14. Maintainability Review

| Aspect | Status | Notes |
|---|---|---|
| Module organization | ✅ Good | Cohesive single-purpose modules; clean `utils/` package; `resilience.py` is a well-factored composition layer |
| Coupling | 🟡 Moderate | Module-level singletons (`db`, `scheduler`, `alerts`) — pragmatic but hinders DI; rate_limiter now swings the other way (per-call, defeating the singleton contract) |
| Type hints | ✅ Clean | 0 mypy errors in 21 source files under project config; CI runs `--strict` |
| Lint cleanliness | ✅ Clean | 0 ruff errors in src/ and tests/ |
| Documentation | 🟡 Stale | README latency targets unmeasurable; `VERIFICATION_RESULTS.md` contradictory; L-DOC-1/L-DOC-2 from FR#1 still open |
| Test coverage | ✅ Gate met | 80.10% ≥ 80% gate; per-module: `ta.py` 63%, `metrics.py` 67%, `options.py` 68%, `scheduler.py` 72%, `alerts.py` 73% — weakest links |
| Test suite hygiene | 🟠 Poor | 6 near-duplicate `test_openalgo_*` files; multiple `_fixed`/`_simple`/`debug_*` scaffolds committed (L-R5-1, L-R5-2) |
| Orphan scaffold | ✅ Fixed | `src/{adapters,modules,orchestrator,risk,rules,strength,strike}.py` removed |
| Tracked artifacts | 🟠 Poor | Prior audit reports + bandit outputs + task_progress committed to main (R5-4) |

---

## 15. Code Quality Review

| Check | Result |
|---|---|
| `ruff check src/ tests/` | ✅ Clean (0 errors) |
| `ruff format --check src/ tests/` | (not run in this review; CI gate exists) |
| `mypy src/loats --config-file pyproject.toml` | ✅ Success: no issues found in 21 source files |
| `mypy src/ --strict --config-file pyproject.toml` (CI command) | (CI-equivalent; project config disables `disallow_any_generics` and `warn_unused_ignores`, which differs from raw `--strict`; L-R5-7) |
| `bandit -r src/loats -c pyproject.toml` | ✅ Clean (0 issues, exit 0) |
| `black --check` | (not run in this review; CI gate exists) |
| Coverage ≥80% | ✅ Pass (80.10%) |

---

## 16. Testing Review

| Aspect | Status | Notes |
|---|---|---|
| Unit tests | ✅ 640 passed, 0 failed | Up from 286 (FR#3) / 325+14fail (FR#4) |
| Integration tests (OpenAlgo) | ✅ Present | `test_openalgo_integration.py`, `test_openalgo_integration_fixed.py` — order paths covered (F-COV-1 resolved: openalgo.py at 94%) |
| Audit hash mutation tests | ✅ Good | `test_audit_hash_mutation.py` |
| VaR / portfolio greeks tests | ✅ Good | `test_portfolio_greeks.py` (NEW-M3 quantity fix covered) |
| Load / latency tests | 🔴 Absent | No performance benchmarks; `test_performance_benchmarks.py` exists but is unit-level |
| Failure-path tests | 🟡 Mixed | Circuit-breaker-open covered; retry-exhausted partially covered; **rate-limiter-exceeded path on order placement NOT covered** (because the limiter is non-functional, see F-CONC-3-R) |
| Test isolation | ✅ Good | `conftest.py` uses `os.environ` (no disk write — L-FIXTURE-1 resolved); `reset_metrics_before_each_test`, `reset_circuit_breakers_before_each_test`, `clear_cache_before_each_test` autouse fixtures |
| Test file bloat | 🟠 Poor | 46 files; many `_fixed`/`_simple`/`debug_*` duplicates (L-R5-1, L-R5-2) |

---

## 17. DevOps Review

| Component | Status | Evidence |
|---|---|---|
| Dockerfile | ✅ Present | Python 3.12-slim; healthcheck; non-root user commented out (security regression — should uncomment) |
| docker-compose | ✅ Present | Resource limits; read-only FS; security_opt; port 8001 exposed (F-MISC-1 resolved) |
| CI (`ci.yml`) | ✅ Strict | ruff+format, isort, mypy --strict, bandit, pip-audit, pytest --cov-fail-under=80, Docker build; **no continue-on-error** (NEW-H3 resolved) |
| CI (`security.yml`) | ✅ Comprehensive | Gitleaks, pip-audit, Bandit, Safety, CycloneDX SBOM; weekly schedule + manual |
| Pre-commit | ✅ Present | `.pre-commit-config.yaml` |
| Secret scanning | ✅ Configured | `.gitleaks.toml` |
| Metrics | 🟠 Misconfigured | Port exposed but server never started (R5-2); compose `CMD` runs only health check (R5-8) |
| Health checks | ✅ Present | `quick_health_check.py`, Docker HEALTHCHECK |
| Runbook | ✅ Present | `RUNBOOK.md` |
| Dependency declaration | ✅ Sound | `pyproject.toml` ↔ `requirements-core.txt` consistent; both LITE-compliant |
| Non-root container | 🟠 Commented out | `Dockerfile:54-58` — the `addgroup`/`adduser`/`USER loats` lines are commented out |

**CI gate status (if run today):** 🟢 **GREEN** — pytest passes (640/640), coverage passes (80.10% ≥ 80%), mypy passes (0 errors), ruff passes (0 errors), bandit passes (0 issues). Only the manual `security.yml` workflow runs `pip-audit` and `safety` (not yet run in this review).

---

## 18. Risk Matrix

| Finding | Severity | Likelihood | Impact | Risk Level |
|---|---|---|---|---|
| F-CONC-3-R (per-call rate limiter) | Critical | Certain | Critical | 🔴 Critical |
| R5-2 (metrics server never started) | Medium | Certain | Medium | 🟠 Medium |
| R5-3 (CB stats race) | Medium | Medium | Low | 🟡 Low-Medium |
| R5-4 (tracked session artifacts) | Medium | Certain | Low | 🟡 Low-Medium |
| R5-8 (Docker CMD never runs app) | Medium | Certain | Medium | 🟠 Medium |
| R5-1 (cache falsy bug + dead params) | Medium | Medium | Low | 🟡 Low-Medium |
| R5-5 (inconsistent HTML escape) | Low | Low | Low | 🟢 Low |
| L-R5-1..8 (hygiene/deprecation) | Low | Certain | Low | 🟢 Low |

---

## 19. Technical Debt Assessment

1. 🔴 **F-CONC-3-R:** Order-path rate limiting is completely defeated. Single biggest blocker.
2. 🟠 **R5-2 + R5-8:** Docker/observability story is half-wired (port exposed, server not started, CMD runs only health check).
3. 🟠 **R5-3:** Circuit-breaker statistics lock discipline incomplete.
4. 🟠 **R5-4 + L-R5-1 + L-R5-2:** Repo hygiene — tracked audit reports, bandit dumps, debug scaffolds, 6 duplicate test_openalgo files.
5. 🟡 **R5-1:** Cache layer carries dead Redis config + falsy-value cache-miss bug.
6. 🟡 **L-FUTURE-1:** `vollib` deprecation (open since FR#1, 2026-07-15).
7. 🟡 **L-DOC-1 / L-DOC-2:** README latency targets unmeasurable; VERIFICATION_RESULTS stale (open since FR#1).
8. 🟡 **R5-6 + L-R5-5:** `MetricsManager` dual-API surface and fragile singleton.

---

## 20. Production Readiness Assessment

**Verdict: NOT READY for live capital. ANALYZE-mode demo only — quality gates green, but one Critical safety regression (F-CONC-3-R) defeats the order-path rate limit.**

| Gate | Status |
|---|---|
| Import / boot | ✅ Pass |
| Tests green | ✅ Pass (640/640) |
| Coverage ≥80% | ✅ Pass (80.10%) |
| Ruff clean | ✅ Pass (0 errors) |
| Mypy clean | ✅ Pass (0 errors in 21 files) |
| Bandit clean | ✅ Pass (0 issues) |
| Packaging installable (`pip install .`) | ✅ Pass (F-DEP-1 resolved) |
| Order placement risk-gated (kill switch) | ✅ Pass |
| Order placement rate-limited | 🔴 **FAIL** (F-CONC-3-R — limiter non-functional) |
| Event loop non-blocking | ✅ Pass (async DB wrappers) |
| Telegram polling correct | ✅ Pass (v20+ lifecycle, F-CONC-2 resolved) |
| Circuit breaker effective | 🟡 Mostly (R5-3 stats race) |
| Fault-tolerance stack functional | ✅ Pass (resilience.py decorator) |
| Audit integrity canonical | ✅ Pass (F-DATA-1 + F-DATA-2 resolved) |
| Docker / CI | 🟡 CI green; Docker half-wired (R5-2, R5-8) |
| Runbook / monitoring | 🟡 Partial (R5-2 metrics server not started) |
| Telegram auth / HTML safety | ✅ Pass (R5-5 minor inconsistencies) |

**Minimum hard requirements before any live deployment:**
1. **Resolve F-CONC-3-R** — restore module-level rate-limiter singletons; invert the regression tests; add a concurrency test that proves the cap is enforced. — **P0**
2. **Resolve R5-2** — wire `start_metrics_server()` into `TradingSystem.initialize()`; expose `metrics_port` in `Settings`. — **P1**
3. **Resolve R5-8** — provide a runtime compose override with `CMD ["python", "-m", "loats.main"]`. — **P1**
4. **Resolve R5-3** — acquire `_state_lock` (or a dedicated `_stats_lock`) when mutating circuit-breaker stats. — **P1**
5. **Resolve R5-1** — remove dead Redis config; fix `get()` falsy-value test. — **P2**
6. **Resolve R5-4** — purge tracked audit reports / bandit dumps / `task_progress.md` from main; add to `.gitignore`. — **P2**
7. **Resolve R5-5** — apply `html.escape()` uniformly to `send_order_alert` / `send_trade_alert`. — **P3**

---

## 21. Prioritized Improvement Roadmap

> REVIEW ONLY — no code changes made. Each item is a concrete work package pending USER APPROVAL.

### P0 — Production blocker (must fix before any order-path goes live)
1. **F-CONC-3-R:** Restore module-level singletons for `get_order_rate_limiter` and `get_smart_order_rate_limiter`. Invert the regression tests at `tests/test_rate_limiter.py:267-276` and `tests/test_rate_limiter_additional.py:307-315` to assert instance identity (same singleton). Add a new concurrency test that fires 100 rapid `place_order` calls through the singleton limiter and asserts that calls beyond `max_ops=50` within a 1-second window raise `RateLimitExceededError`. *(Estimated: 1 hour)*

### P1 — Correctness / Observability / Deployment
2. **R5-2:** Add `metrics_port: int = 8001` to `Settings`; call `start_metrics_server(settings.metrics_port)` inside `TradingSystem.initialize()` after `initialize_cache()`. Verify the JSON endpoint responds on `http://localhost:8001/`. *(Estimated: 30 minutes)*
3. **R5-8:** Create `docker-compose.prod.yml` (or override) with `command: ["python", "-m", "loats.main"]`; keep `docker-compose.yml` for CI health-check use. Document the split in README. *(Estimated: 1 hour)*
4. **R5-3:** Acquire `self._state_lock` inside `_record_success` and `_record_failure` when modifying `self._stats` or `self._state`. Alternatively, add a dedicated `self._stats_lock` to avoid contention with the state-readers. Add a thread-concurrency test that exercises parallel sync + async calls. *(Estimated: 1 hour)*

### P2 — Robustness / Hygiene
5. **R5-1:** Remove `redis_host`, `redis_port`, `redis_password` from `CacheConfig.__init__` and its docstring. Replace `if result is not None` for the cache-miss sentinel test in `cache.py:111-113`. Add a regression test that caches `0`, `0.0`, `""`, `False`, `[]` and verifies they are returned as cached values rather than triggering a re-fetch. *(Estimated: 30 minutes)*
6. **R5-4:** Remove from git: `01August2026-Forensic-Engineering-Audit-FR4.md`, `VERIFICATION_RESULTS.md` (or regenerate), `bandit_output.json`, `bandit_output.txt`, `bandit_output_final.json`, `bandit_output_fixed.json`, `task_progress.md`. Add `*Forensic*Audit*.md`, `bandit_output*.json`, `bandit_output.txt`, `qg_*.txt`, `task_progress.md`, `*_audit.md` to `.gitignore`. *(Estimated: 15 minutes)*
7. **R5-5:** Apply `html.escape()` to `order.order_id`, `order.symbol`, `order.order_type.value`, `order.transaction_type.value` in `send_order_alert` (alerts.py:326-337); same for `trade.trade_id`, `trade.symbol`, `trade.strategy`, `trade.transaction_type.value` in `send_trade_alert` (alerts.py:371-381). *(Estimated: 30 minutes)*
8. **L-R5-1 / L-R5-2:** Consolidate `test_openalgo*.py` (6 files) into a single canonical `test_openalgo.py` after merging coverage. Move debug scaffolds (`debug_kill_switch.py`, `test_kill_switch_fixed.py`, `test_kill_switch_simple.py`, `test_final_logging_verification.py`, `test_logging_implementation.py`) to `tests/scratch/` or delete. Re-run full suite to confirm no coverage regression. *(Estimated: 2 hours)*

### P3 — Hygiene / Tech Debt
9. **L-R5-3:** Sync `.env.example` — remove the three `NIM_*` env vars; verify all other vars map to real `Settings` fields.
10. **L-R5-7:** Align `pyproject.toml [tool.mypy]` with CI's `--strict` (set `disallow_any_generics = true`, `warn_unused_ignores = true`) or change CI to `mypy src/ --config-file pyproject.toml` (drop `--strict`).
11. **L-FUTURE-1:** Plan migration off deprecated `vollib` (open since 2026-07-15). Evaluate `py_vollib` successor or `QuantLib`.
12. **L-DOC-1 / L-DOC-2:** Update README to remove `<5ms strike` / `<100ms cycle` claims (no strike/orchestrator module exists); regenerate `VERIFICATION_RESULTS.md` from live command output after the above fixes land.
13. **R5-6 + L-R5-5:** Refactor `MetricsManager` to use `@functools.lru_cache(maxsize=1)` factory instead of `__new__`-based singleton; collapse the dual Prometheus-stub/direct-method API into one.
14. **Dockerfile non-root:** Uncomment the `addgroup`/`adduser`/`USER loats` block in `Dockerfile:54-58` to run as non-root.

---

## Appendix A — Verification Commands (re-runnable, evidence basis for this review)

```powershell
# Import smoke test (PASS)
python -c "from src.loats.main import TradingSystem; print('OK')"

# Full suite with coverage gate (PASS — 640 passed, 80.10% coverage)
python -m pytest tests/ --cov=src/loats --cov-branch --cov-fail-under=80 -q

# Quality gates (ALL PASS)
python -m ruff check src/ tests/ --config pyproject.toml      # All checks passed!
python -m mypy src/loats --config-file pyproject.toml         # Success: no issues found in 21 source files
python -m bandit -r src/loats -c pyproject.toml               # 0 issues, exit 0
```

```powershell
# F-CONC-3-R reproduction (proves the limiter is non-functional)
python -c @"
import asyncio
from src.loats.utils.rate_limiter import get_order_rate_limiter
async def main():
    l1 = get_order_rate_limiter()
    l2 = get_order_rate_limiter()
    print('same instance?', l1 is l2)  # False — singleton defeated
    # 100 acquires in a tight loop:
    results = [await get_order_rate_limiter().acquire() for _ in range(100)]
    print('all True?', all(results), '— count:', sum(results))  # 100 True — no throttling
asyncio.run(main())
@"
```

---

## Appendix B — Prior-Review Finding Disposition (Verified 2026-08-08)

| Prior Finding | Source | Status | Evidence |
|---|---|---|---|
| B1–B7 (import chain blockers) | FR#1 (15July) | ✅ Resolved | `python -c "from src.loats.main import TradingSystem"` succeeds |
| H1–H9 (correctness/financial) | FR#1 | ✅ Resolved | portfolio greeks use `contract.quantity` (options.py:632); ExpiredContractError raised; hardcoded test values removed |
| M1–M11 (robustness) | FR#1 | ✅ Resolved | Windows signal handler; IST weekday check; async newspaper I/O; structlog ordering; `extra="ignore"` |
| L1–L8 (hygiene) | FR#1 | 🟡 Partial | L1 (README), L2 (VERIFICATION_RESULTS), L8 (uuid IDs) addressed; L-FUTURE-1 (vollib) still open |
| F-CONC-1 (sync DB in async) | FR#2 | ✅ Resolved | `database.py` async wrappers via `asyncio.to_thread`; scheduler uses `await self.db.async_*` |
| F-CONC-2 (run_polling blocks) | FR#2 | ✅ Resolved | `alerts.py:122-155` uses v20+ lifecycle (initialize → start → updater.start_polling as task) |
| F-SEC-1 (raw SQL) | FR#2 | ✅ Resolved | `execute_query`/`get_dataframe` removed |
| F-REL-1 (kill switch unwired) | FR#2 | ✅ Resolved | `_check_kill_switch` / `_async_check_kill_switch` in all order paths |
| F-CONC-3 (rate limiter per-call) | FR#2 | 🔴 **REGRESSED** | **F-CONC-3-R** — commit `87cf065` re-introduced per-call factories |
| F-SEC-2 (HTML injection) | FR#2 | ✅ Mostly resolved | R5-5 — minor inconsistencies remain in `send_order_alert`/`send_trade_alert` |
| F-CONC-4 (Database() per /signals) | FR#2 | ✅ Resolved | `AlertSystem` accepts injected `Database` (alerts.py:50); falls back to module singleton |
| F-CONC-5 (dual error contracts) | FR#2 | 🟡 Unchanged | Sync envelope vs async-raise persists; not actively harmful |
| F-DATA-1 (non-canonical hash) | FR#2 | ✅ Resolved | `_canonical_serialize` + `_canonical_normalize` used by both `_calculate_sha256` and `verify_audit_log_integrity` |
| F-DATA-2 (JSONL write path) | FR#4 | ✅ Resolved | `database.py:570` writes via `_canonical_serialize(entry_data)` |
| NEW-H1 (exception chaining) | FR#3 | ✅ Resolved | `raise ... from e` throughout |
| NEW-H2 (thread-local DB close) | FR#3 | ✅ Resolved | `main.shutdown()` calls `await self.db.async_close_all()` |
| NEW-H3 (CI continue-on-error) | FR#3 | ✅ Resolved | `ci.yml` has no `continue-on-error` |
| NEW-M1 (HTML injection) | FR#3 | ✅ Resolved | R5-5 minor follow-up |
| NEW-M2 (.env.example sync) | FR#3 | 🟡 Partial | L-R5-3 — `NIM_*` vars remain |
| NEW-M3 (quantity hardcoded) | FR#3 | ✅ Resolved | `contract.quantity` at options.py:632 |
| NEW-M4 (negative t clamped) | FR#3 | ✅ Resolved | `ExpiredContractError` raised at options.py:115, 180, 256, 358, 416 |
| NEW-M5 (per-command Database) | FR#3 | ✅ Resolved | `AlertSystem(database=...)` DI; `db` property resolves module singleton lazily |
| NEW-L1 (__all__ bug) | FR#3 | ✅ Resolved | `__all__` matches imports |
| NEW-L2 (eager settings) | FR#3 | ✅ Resolved | Lazy `lru_cache` + PEP 562 `__getattr__` |
| F-DEP-1 (missing pyproject deps) | FR#4 | ✅ Resolved | `cachetools` added; redis/prometheus removed (LITE route) |
| F-ARCH-1 (Redis vs LITE) | FR#4 | ✅ Resolved | Redis removed; in-memory `TTLCache` |
| F-TEST-1 (14 failures) | FR#4 | ✅ Resolved | 640/640 passing |
| F-CONC-6 (await dict composition) | FR#4 | ✅ Resolved | `utils/resilience.py` decorator composition; 0 mypy errors |
| F-TYPE-1 (27 mypy errors) | FR#4 | ✅ Resolved | 0 mypy errors |
| F-LINT-1 (28 ruff errors) | FR#4 | ✅ Resolved | 0 ruff errors |
| F-COV-1 (openalgo.py 65%) | FR#4 | ✅ Resolved | openalgo.py at 94% |
| F-CONC-7 (sync decorator async) | FR#4 | ✅ Resolved | `rate_limited`/`async_rate_limited` decorators removed |
| F-LOG-1 (malformed log calls) | FR#4 | ✅ Resolved | 0 malformed calls |
| F-CONC-8 (_polling_task init) | FR#4 | ✅ Resolved | `alerts.py:63` declares `self._polling_task: asyncio.Task[Any] | None = None` |
| F-MISC-1 (port mismatch) | FR#4 | ✅ Resolved | `docker-compose.yml:41` exposes 8001 |
| F-MISC-2 (nim_rate_guard omit) | FR#4 | ✅ Resolved | pyproject omit list no longer references it |
| L-FIXTURE-1 (.env.test disk write) | FR#4 | ✅ Resolved | conftest.py:162-169 uses `os.environ` |
| L-FUTURE-1 (vollib deprecation) | FR#1 | 🟡 Open | Still uses `vollib>=1.0.1` |
| L-DOC-1 (README stale) | FR#1 | 🟡 Open | Latency targets still unmeasurable |
| L-DOC-2 (VERIFICATION_RESULTS) | FR#1 | 🟡 Open | Stale; contradictory to live evidence |

---

## Appendix C — New Findings Introduced in FR#5 (This Review)

| ID | Severity | One-line |
|---|---|---|
| F-CONC-3-R | 🔴 Critical | Order-path rate limiters create fresh instance per call (regression of FR#2 F-CONC-3) |
| R5-1 | 🟡 Medium | Cache layer carries dead Redis config + `get()` treats cached `0`/`""`/`False` as miss |
| R5-2 | 🟡 Medium | Metrics HTTP server never started by `main.initialize()` |
| R5-3 | 🟡 Medium | Circuit-breaker stats mutated without lock (sync+async race) |
| R5-4 | 🟡 Medium | Tracked audit reports + bandit dumps + task_progress pollute repo |
| R5-5 | 🟢 Low | HTML escaping inconsistent across alert message builders |
| R5-6 | 🟢 Low | `MetricsManager.__new__`-based singleton fragile |
| R5-7 | 🟢 Low | `_safe_get_*` helpers contain unreachable `except CircuitBreakerOpenError` branches |
| R5-8 | 🟡 Medium | Docker `CMD` runs only `quick_health_check.py`; trading system never starts |
| L-R5-1..8 | 🟢 Low | Test file duplicates; stale `.env.example` NIM vars; mypy strict/config drift; vollib deprecation carried forward |

---

**End of Forensic Review #5. This is a REVIEW-ONLY deliverable. No code has been modified. All recommendations require explicit USER APPROVAL before implementation. The quality gates are green (640/640 tests, 80.10% coverage, ruff/mypy/bandit clean), but ONE Critical safety regression (F-CONC-3-R) must be resolved before any order-placement path is exercised against live capital.**
