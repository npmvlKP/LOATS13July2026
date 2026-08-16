# LOATS13July2026 — Final Forensic Engineering Report (FR-FINAL — Consolidated Investigator + Reviewer)

**Date:** 2026-08-15
**Project:** LOATS13July2026 — Lite OpenAlgo Trading System (Indian equities/options research; OpenAlgo broker API; Telegram alerts; APScheduler + orchestrator analysis pipeline)
**Repository:** https://github.com/npmvlKP/LOATS13July2026.git (HEAD `36d0c52`, 2026-08-15 19:10 IST; working tree clean apart from untracked review artifacts)
**Python:** 3.12.7 — clean venv `G:\.OA\LOATS-13July2026\LOATS13July2026\LOATS13July2026\`
**Master plan audited against:** `LOATS-CMP-13July2026.txt` (Compact Master Plan, "LITE" edition)
**Mode:** REVIEW ONLY — no code modified, no patches generated, no destructive operations executed. Every recommendation is conditional on explicit USER APPROVAL.

**Reviewers (Senior Engineering Review Board):** Principal Software Architect · Senior Python Engineer · Senior Code Reviewer · Production Debugging Engineer · Performance Optimization Engineer · Scalability Engineer · Security Auditor · DevOps & Infrastructure Engineer · QA / Test Architect · Reliability Engineer (SRE) · Technical Lead · Systems Design Reviewer

**Consolidation basis:** This report merges the two same-day forensic passes — the Investigator audit (FR6, `15Aug2026-CaveCrewInvestigator-Forensic Report.md`) and the independent Reviewer verification (FR6-R, `15Aug2026-CaveCrew Reviewer-Forensic Report.md`). The Reviewer re-verified every Investigator finding with live evidence in the clean venv at HEAD `36d0c52`: **zero refutations, zero material contradictions.** Where the passes differ, the Reviewer's refinement wins and is noted (F6-C-01 root-cause refinement; F6-M-06 quantified worse; F6-M-02 flaky-test status).

**Evidence basis (all live, clean venv, HEAD `36d0c52`):**
`git rev-parse/log/status`; empirical rate-limiter probe (singleton identity, effective cap, 100-acquire burst — reproduced identically in both passes); `check_deps_sync.py` PASS; `ruff check` **FAIL — 135 errors** (101×E501, 17×RUF003, 9×RUF001, 8×RUF002; 112 in `src/`); `ruff format --check` **FAIL — 20 files**; `isort --check-only` **FAIL — 11 files**; `flake8` PASS; `mypy --strict` PASS (27 files); `bandit` PASS; `pip-audit` PASS; `pytest` **843 passed / 0 failed / 9 warnings, 116.60s, coverage 80.43%** (gate ≥80 met; Investigator run recorded 80.41% — timing jitter, both clear the gate); per-module coverage table; source reads of `orchestrator.py`, `rate_limiter.py`, `settings.py`, `openalgo.py` call sites, `database.py:655`, `cache.py:23-29`, `strike_selection.py`, `check_per_module_coverage.py`, `Dockerfile`, `pyproject.toml`; git inventory (302 tracked files; 38 root-level `.py`; 38 root-level `.md`); grep sweeps confirming CMP-scope absences (no `rules.py`, no `strength.py`, no ADX/BBANDS/CCI/Hurst/regime, no `TradeDecision`, no order-modification counter, no `date.today()`); byte-level mojibake scan (0×U+FFFD in `src/`).

---

## 1. Executive Summary

### 1.1 Verdict

**The project is NOT built strictly as per `LOATS-CMP-13July2026.txt`.** It is a substantially conformant LITE build (~70% of plan scope) with **one Critical compliance deviation** (the CMP's loudest non-negotiable — self-limit ≤3 OPS — is configured but unwired, effective cap 50 OPS), **red quality gates at HEAD**, and the CMP's strategy core (Rules, Strength, sizing, trailing ratchet, VaR, session lifecycle, TradeDecision→Analyzer routing) absent.

**NOT READY for live capital. ANALYZE-mode demo only — and current HEAD does not pass its own CI.**

### 1.2 CMP demand vs build reality (verified live, both passes)

| CMP requirement | State at HEAD `36d0c52` | Verdict |
|---|---|---|
| LITE: zero services, no Docker deps, pip-only | SQLite WAL + JSONL audit, in-memory TTLCache, stdlib metrics :8001; no Redis/Prometheus services | ✅ Conformant |
| Pipeline: Sentiment → TA/VA → **Strength** → **Rules** → Strike → Risk → Orchestrator | Sentiment ✅, TA ✅ (partial indicator set), Strike ✅ (`strike_selection.py`), Risk partial (kill switch, margin/position checks), Orchestrator ✅ — **`strength.py` and `rules.py` DO NOT EXIST** (module list verified: 25 `.py` files under `src/loats/`) | 🟠 Partial — 2 of 8 stages missing |
| **Zero-Assumption Rule 4: OPS threshold 10 (NSE/INVG/67858); self-limit ≤3 OPS** | `Settings.max_ops = 3` exists (`settings.py:82`) but limiter factories hard-code **50**; order-path call sites pass no argument (`openalgo.py:799, 876`); **live probe (both passes): singleton identity True, effective max_ops 50, 50/100 acquires pass** | 🔴 **VIOLATED — Critical** |
| Rule 11: position limits 5 NIFTY / 3 BANKNIFTY | `max_position_size = 1000`, `max_position_per_symbol = 1000` (`settings.py:88-96`) — **~200× the CMP rule**; orchestrator checks against 1000 (`orchestrator.py:404`) | 🔴 VIOLATED |
| Rule 7: order modification limit 25/order | No modification counter anywhere (grep-verified) | 🔴 Not implemented |
| Rules 6/12: bot-logic trailing SL + SL-M monotonic ratchet | `OrderType.SL_M` exists; `trailing_stop_loss` is stored/passed through only (models/DB/payload) — no ratchet engine | 🟠 Partial |
| Audit: SHA-256 chain, append-only, 7-yr | Canonical SHA-256 + JSONL-first dual-write; `retention_days=2555` — but JSONL write **skipped under pytest** (`database.py:655`) | ✅ Conformant (test-mode caveat §8) |
| Verification every PR: ruff, mypy --strict, bandit, pytest cov ≥80%, pip-audit | All present in CI **plus** isort/flake8/deps-sync/per-module-coverage/gitleaks — but **ruff (135), ruff-format (20 files), isort (11 files) FAIL at HEAD today** | 🔴 Gates red at HEAD |
| Latency gates: strike <5ms, cycle <100ms | Instrumented: 4ms strike `wait_for` + 5ms warning + fallback (`orchestrator.py:461-477`); 100ms cycle budget — unvalidated against live data | ✅ Implemented (unvalidated) |
| Repo structure per CMP §4 (connectors/strategy/risk packages) | Flat `src/loats/` package; functional equivalents exist for strike/orchestrator/kill-switch/audit; missing: connectors, strategy/rules, risk/manager, strength | 🟠 Deviation + gaps |
| Git hygiene (compact repo, secrets in `.env` only) | `.env` untracked ✅, secrets contained ✅ — but 302 tracked files incl. **38 root `.py` + 38 root `.md`** artifacts | 🔴 Violated in spirit |

Full clause-by-clause matrix: **Appendix A**.

### 1.3 Scorecard across the seven reviews

| Dimension | FR4 (01Aug) | FR5 (08Aug) | FR6 Investigator (15Aug) | **FR6-R Reviewer (15Aug)** | Trend |
|---|---|---|---|---|---|
| Tests | 325/14 fail | 640/0 | 843/0 (1 flaky seen) | **843/0 (flaky NOT reproduced)** | ✅ Up |
| Coverage (aggregate) | 79.17% | 80.10% | 80.41% | **80.43%** | ✅ Gate met |
| Ruff | 28 errors | 0 | 135 errors | **135 errors (re-run, exact match)** | 🔴 Regressed |
| Ruff format / isort | — | clean | 20 / 11 files | **20 / 11 files (re-run, exact match)** | 🔴 Regressed |
| Mypy `--strict` | 27 errors | 0 | 0 (27 files) | **0 (re-run: "Success: no issues found in 27 source files")** | ✅ Held |
| Flake8 / bandit / pip-audit / deps-sync | mixed | clean | clean | **all PASS (re-run)** | ✅ Held |
| Order-path rate limit | broken (per-call) | broken | singleton @ **50 OPS** | **confirmed @ 50 OPS (probe)** | 🟠 Half-fixed |
| CMP strategy core | absent | absent | absent | **absent (re-verified by grep + module list)** | 🟠 Unchanged |
| Repo hygiene | poor | poor | 302 files | **302 tracked; 38 root `.py`; 38 root `.md`** | 🔴 Worse |

### 1.4 The three things that matter most

1. **F6-C-01 (Critical, compliance/capital):** the order-path rate limiter now works as a true singleton — but its process-wide default is hard-coded `max_ops=50` while `Settings.max_ops=3` (CMP-mandated self-limit; NSE INVG/67858 threshold 10 OPS) is dead configuration. Verified empirically in both passes: 50 of 100 rapid acquires succeed. Note the bitter irony: HEAD's own commit message documents "Acquire enforces max_ops=50 per second" as the *intended* behavior — the wrong value is now codified, not accidental.
2. **F6-C-02 (Critical, process):** HEAD fails three of its own CI gates (ruff 135, ruff-format 20, isort 11) while commit messages continue claiming readiness ("READY FOR PRODUCTION" `694a377`; "Ruff linting passed" `002dac5`; "89.02% coverage maintained" `3d6a677` vs actual 80.43%; "All 843 tests pass, confirming correct throttling" `36d0c52`). The misleading-commit pathology (R5b-F-NEW-1) is ongoing and now measurable.
3. **F6-H-04 (High, scope):** the CMP's trading-strategy core is absent: no `rules.py` (IV-rank/ADX/VIX gates), no `strength.py` (≥3-source composite), no 2% fixed-fractional sizing, no monotonic trailing-ratchet SL-M engine, no historical VaR, no session lifecycle (PRE_OPEN→REGULAR→POST_CLOSE), no `TradeDecision` object, no Analyzer routing. What exists is a competent data/TA/sentiment/orchestration scaffold — not yet the CMP trading system.

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
├── database_async_additions.py         # monkey-patch module adding true-async aiosqlite methods (31% cov)
├── openalgo.py                         # sync+async clients; kill switch; CB on ALL paths; Idempotency-Key
├── alerts.py                           # Telegram v20+; admin allow-list; CB-protected; html.escape
├── scheduler.py                        # APScheduler; IST+weekday+NSE-holiday aware; shared db singleton
├── orchestrator.py                     # 100ms cycle loop; TA→(sentiment‖market)→signal→risk (57% cov)
├── strike_selection.py                 # <5ms strike engine (atm_straddle/delta_neutral/oi_based)
├── sentiment.py / ta.py / options.py   # VADER+RSS; RSI/MACD/ATR/Supertrend/VWAP/CMF; BS/Greeks/IV
├── main.py                             # TradingSystem lifecycle; metrics server; orchestrator start/stop
└── utils/
    ├── cache.py                        # TTLCache (asyncio.Lock); stray optional redis import (F6-L-02)
    ├── circuit_breaker.py              # CLOSED/OPEN/HALF_OPEN; _state_lock; module breakers (99% cov)
    ├── connection_pool.py              # aiosqlite pool wrapper (97% cov)
    ├── payload_builder.py              # shared order-payload builder — dedupe fix (100% cov)
    ├── rate_limiter.py                 # singleton factories (async+sync) — hard-coded 50 default (F6-C-01)
    ├── resilience.py                   # circuit_breaker_retry_{sync,async} decorators
    └── retry.py                        # exponential backoff + jitter
```

**Runtime lifecycle:** `TradingSystem.initialize()` → metrics server (`main.py:49`) → `db.async_initialize()` + audit verify → alerts/scheduler init → `start()` → `alerts.start()` (non-blocking poll) + `scheduler.start()` + `start_orchestrator()` (`main.py:55`) → shutdown: `stop_orchestrator()` → scheduler → alerts → `async_close_all()`.

**Architectural deltas since FR5 (verified):**
1. **Orchestrator + strike selection added** (CMP P5/P4 scope) — wired into `main`.
2. **True-async DB tier added**: `aiosqlite`; three overlapping persistence mechanisms (sqlite3 thread-local, aiosqlite pool, `to_thread` fallback) — powerful, weakly governed (F6-H-03).
3. **Payload dedupe**: shared `utils/payload_builder.py` (closes L-R5-10).
4. **Singleton rate limiters restored** with per-factory locks, custom-key caches, `_reset_singletons_for_testing()` — mechanically correct, wrong value (F6-C-01).

---

## 3. Reverse Engineered Data Flow

```
                 ┌────────────────────────── TradingSystem (main.py) ──────────────────────────┐
                 │  metrics :8001   alerts (Telegram poll)   scheduler (APScheduler jobs)      │
                 └──────────────────────────────────┬─────────────────────────────────────────┘
                                                    │
                      orchestrator._run_cycle_loop (100ms budget, kill-switch gated)
                          │
          TA (seq, pre-window) ──► (sentiment ‖ market-data) 80ms parallel window ──► combined signal ──► risk checks
                          │                                                            │
                          ▼                                                            ▼
   AsyncOpenAlgoClient (CB+retry on GETs; CB+kill-switch+rate-limit on order POSTs)   db.async_* (aiosqlite pool → to_thread fallback)
                          │                                                            │
                          │ Idempotency-Key (UUID v4; cancel/modify keyed by           ▼
                          │ order_id; place keyed by payload digest)        SQLite WAL + JSONL audit (JSONL-first, canonical SHA-256)
                          ▼
                    OpenAlgo REST (127.0.0.1:5000, ANALYZE default)
```

**Order path (financial-critical), verified line-level in both passes:**
`place_order` → `_async_check_kill_switch()` → `get_order_rate_limiter().acquire()` (`openalgo.py:799` — **default 50/s, F6-C-01**) → CB open-check (fail-fast) → `_request(..., idempotency_key=...)` → `Idempotency-Key` header (`openalgo.py:245,605`) + DB duplicate-order guard (`database.py:1466-1476`). Kill-switch block writes an audit entry. Smart-order path identical at `openalgo.py:876`.

**Async boundary:** orchestrator/scheduler/alerts on one event loop; aiosqlite pool spans worker threads; legacy sqlite3 via `to_thread`; RSS/newspaper via `to_thread`+`gather`. No sync-DB-in-async regressions (FR2 F-CONC-1 stays closed). Known loop-hygiene exceptions: orchestrator TA stage runs sequentially *before* the 80ms parallel window, so a slow `get_history` (httpx timeout 30s) can stall the cycle far beyond the 100ms budget (F6-H-05.7).

---

## 4. Dependency Overview

| Dependency | pyproject | requirements-core | Verdict |
|---|---|---|---|
| openalgo, httpx, pydantic(-settings), APScheduler, numpy, pandas, scipy, vaderSentiment, feedparser, newspaper4k, structlog, python-telegram-bot, python-dotenv | ✅ | ✅ | ✅ Synced (gate-enforced) |
| lxml, lxml-html-clean, cryptography, cachetools | ✅ | ✅ | ✅ R5-F-22 closed |
| **aiosqlite** `>=0.21.0` | ✅ | ✅ | ✅ NEW — LITE-compatible (pure Python) |
| ta `>=0.11.0` | ✅ | ✅ | 🟡 Declared but **unused in code** (custom `ta.py` instead) — adopt or drop |
| vollib `>=1.0.11` | ✅ | ✅ | 🟡 CMP rule 9 says `py_vollib`; `vollib` is the ecosystem successor — deliberate, documented deviation (VOLLIB_MIGRATION_PLAN.md) |
| redis | ❌ | ❌ | 🟡 Not a dependency, but `utils/cache.py:23-29` retains a guarded optional `import redis.asyncio` + unused `REDIS_AVAILABLE` — dead LITE-drift code (F6-L-02) |

`scripts/check_deps_sync.py` runs as a CI gate and **PASSES (re-run)** — manifest drift is now mechanically prevented. pip-audit: no known vulnerabilities (local package skipped — not on PyPI).

---

## 5. Module-by-Module Review

Coverage figures from the live run (843 tests, branch coverage on):

| Module | Stmts | Cover | Verdict | Key notes |
|---|---|---|---|---|
| `utils/payload_builder.py` | 54 | **100%** | ✅ Good | Shared order-payload builder; closes L-R5-10 duplication |
| `loats_logging.py` | 20 | **100%** | ✅ Good | structlog-first ordering |
| `utils/circuit_breaker.py` | 139 | **99%** | ✅ Good | Best-tested module; `_state_lock` discipline |
| `models.py` | 231 | 94% | ✅ Good | uuid4 IDs; enum-safe PnL; SL_M; idempotency_key |
| `sentiment.py` | 109 | 93% | ✅ Good | VADER ±0.05; to_thread+gather |
| `options.py` | 255 | 90% | ✅ Good | BS/Greeks; brentq+newton IV; `ExpiredContractError` |
| `utils/resilience.py` | 83 | 89% | ✅ Good | CB+retry composition (F-CONC-6 stays closed) |
| `main.py` | 125 | 88% | ✅ Good | Metrics server started; orchestrator wired; Windows-safe signals |
| `utils/retry.py` | 89 | 87% | ✅ Good | Backoff+jitter, sync+async |
| `ta.py` | 298 | 86% | ✅ Good | Vectorized NumPy; **CMP indicator gaps** (no ADX/BBANDS/CCI/Hurst/regime — grep-verified) |
| `metrics.py` | 183 | 85% | ✅ Good | Stdlib HTTP :8001; single API path post-refactor |
| `database.py` | 510 | 85% | ✅ Good | Canonical hash; thread registry; **test-mode JSONL bypass (F6-M-01)** |
| `utils/cache.py` | 201 | 84% | 🟠 Issues | TTLCache + `asyncio.Lock` (loop-scope only — not thread-safe for `to_thread` callers); redis ghost import |
| `config/settings.py` | 82 | 96% | ✅ Good | Lazy; validators; **`max_ops=3` dead config (F6-C-01)** |
| `alerts.py` | 474 | **79%** | 🟠 Below 80 | Telegram v20+; admin allow-list; html.escape; broad `except` paths untested |
| `scheduler.py` | 371 | **76%** | 🟠 Below 80 | NSE holidays (32 tests); shared db singleton; job-error paths untested |
| `strike_selection.py` | 122 | **74%** | 🟠 Below 80 | 4ms guard + fallback; **unbounded `_cache` dict (F6-M-04)** |
| `utils/rate_limiter.py` | 211 | **72%** | 🔴 Defect | Singleton factories work; **hard-coded 50 default (F6-C-01)**; factory custom-key paths untested (miss lines 429-482) |
| `orchestrator.py` | 304 | **57%** | 🔴 Defects | 7 correctness defects (F6-H-05); newest core module, second-worst coverage |
| `database_async_additions.py` | 227 | **31%** | 🔴 Defects | Production-preferred DB path, least-tested code; aiosqlite thread teardown exceptions observed live (`PytestUnhandledThreadExceptionWarning`) |

---

## 6. Critical Findings (Priority P0)

### 🔴 F6-C-01 — Order-path rate limiter enforces 50 OPS; CMP self-limit (≤3) and NSE threshold (10) unwired

- **Issue ID:** F6-C-01
- **Category:** Compliance / Financial Safety
- **Severity:** Critical · **Confidence:** Certain (empirical, reproduced identically in BOTH passes)
- **Owning specialists:** Production Debugging Engineer, Security Auditor, Reliability Engineer
- **Evidence (clean venv, HEAD `36d0c52`):**
  - Probe output (verbatim, identical in both passes):
    ```
    singleton identity: True
    effective max_ops: 50
    window_size: 1.0
    settings.max_ops: 3
    order acquires passed: 50 /100
    smart acquires passed: 50 /100
    ```
  - `src/loats/utils/rate_limiter.py` — all four factory functions (`get_order_rate_limiter` :355, `get_smart_order_rate_limiter` :389, plus sync variants :421/:455) hard-code `max_ops=50` when no argument is supplied.
  - Order-path call sites pass **no argument**: `openalgo.py:799` `if not await get_order_rate_limiter().acquire():` and `openalgo.py:876` (smart).
  - `config/settings.py:82` — `max_ops: int = Field(3, ...)`; zero references to `settings.max_ops` in the factory path (grep-verified).
  - **Root-cause refinement (Reviewer pass):** the limiter **class constructors already default correctly** — `rate_limiter.py:35/139/254`: `self.max_ops = max_ops if max_ops is not None else settings.max_ops`. The factories defeat this by explicitly passing `max_ops=50`. The fix is therefore one line per factory: pass through `None`/`settings.max_ops` instead of `50`.
  - Commit `36d0c52` (HEAD) message states "Acquire enforces max_ops=50 per second" as intended behavior — the wrong cap is codified in the project's own history.
- **Root cause:** The R5-F-01 singleton fix baked the regression-era value (50) in as the factory default; the CMP-mandated knob (`Settings.max_ops=3`) was never plumbed through, despite the class layer already supporting it.
- **Technical explanation:** A sliding-window limiter enforces ≤N ops/window only if the singleton's N equals the mandated cap. With N=50, the loop permits 50 orders/sec — **5× the NSE/INVG/67858 registration threshold (10 OPS)** and **~17× the CMP self-limit (3)**.
- **Impact / possible consequences:** Broker throttling/IP ban, SEBI exposure, uncontrolled capital placement from a runaway loop or flooded Telegram handler; the one control the CMP marks NON-NEGOTIABLE is defeated by configuration drift.
- **Risk assessment:** Critical — compliance + capital.
- **Suggested resolution (pending approval):** In each factory default `max_ops` from `get_settings().max_ops` (or pass `None` and let the constructor default apply); add a regression test asserting `get_order_rate_limiter().max_ops == settings.max_ops`; add a CI assertion that the effective cap ≤ 10.
- **Estimated complexity:** Low (30 min incl. tests). **Dependencies:** none. **Priority:** **P0**.

### 🔴 F6-C-02 — HEAD fails three of its own CI quality gates; commit claims contradict the tree

- **Issue ID:** F6-C-02
- **Category:** Process / Quality Gates
- **Severity:** Critical (blocks merge; false history) · **Confidence:** Certain (live runs, identical counts in both passes)
- **Owning specialists:** Technical Lead, QA / Test Architect, DevOps & Infrastructure Engineer
- **Evidence (clean venv, HEAD `36d0c52`):**
  - `ruff check src/ tests/ scripts/` → **135 errors** (statistics: 101×E501 line-too-long, 17×RUF003, 9×RUF001, 8×RUF002 ambiguous-unicode; `src/` alone: 112 errors).
  - `ruff format --check` → **20 files** would be reformatted (incl. `src/loats/alerts.py`, `src/loats/openalgo.py`, `src/loats/utils/cache.py`).
  - `isort --check-only` → **11 files** (10 in `tests/` incl. `conftest.py`, `test_orchestrator.py`, `test_rate_limiter.py`; 1 in `scripts/commit_message_check.py`).
  - Contrast (same tree): mypy `--strict` "Success: no issues found in 27 source files"; flake8 exit 0; bandit exit 0; deps-sync PASS; pytest 843/0, cov 80.43% PASS.
  - Misleading commit evidence (git log): `694a377` "__R5-F-01 / F-CONC-3-R Status:__ ✅ __READY FOR PRODUCTION__"; `002dac5` "Code Quality: Ruff linting passed … Production Ready" (contradicted by 135 errors); `3d6a677` "89.02% coverage maintained" (aggregate is 80.43%); HEAD `36d0c52` "All 843 tests pass, confirming correct throttling" (tests pass; the *throttling value* is wrong per F6-C-01).
- **Root cause:** Final pushes bypassed pre-commit/CI (no required status checks on `main`); AI-authored smart-quote/en-dash text bled into docstrings (RUF001-003) alongside long lines; commit messages written as status claims rather than change descriptions.
- **Technical explanation:** Three of nine gates red means CI on this HEAD fails; any "green" claim in history is false. The RUF001-003 classes indicate non-ASCII lookalike characters in strings/comments/docstrings — cosmetic but rule-flagged, and a readability hazard in a financial codebase.
- **Impact / possible consequences:** Red CI; false confidence from `git log`; process controls (CONTRIBUTING.md, `commit_message_check.py`) exist and are routinely violated by the very commits that add them.
- **Risk assessment:** Critical (process) — the project cannot merge or release from this HEAD.
- **Suggested resolution (pending approval):** `ruff check --fix` + `ruff format` + `isort`; normalize the 34 ambiguous-unicode literals; re-run all gates to green; enable branch protection requiring CI on `main`; enforce the existing commit-message hook.
- **Estimated complexity:** Low (≈1 h). **Dependencies:** none. **Priority:** **P0**.

---

## 7. High Priority Findings (Priority P1)

### 🟠 F6-H-03 — aiosqlite tier: 31% coverage, event-loop teardown defects, ungoverned tri-modal persistence

- **Issue ID:** F6-H-03 · **Category:** Reliability / Testing · **Severity:** High · **Confidence:** Certain (both passes)
- **Evidence:** `database_async_additions.py` **31%** covered (miss lines 33-300+: the true-async bodies); pytest run emits `PytestUnhandledThreadExceptionWarning` from aiosqlite worker threads ("Event loop is closed" — reproduced live in both passes); `database.py:1788` pool `maxsize=10`; async methods dispatch aiosqlite-pool → `to_thread` fallback while legacy sqlite3 thread-locals persist.
- **Root cause:** New async tier bolted on via monkey-patch module; pool lifecycle not joined on shutdown; tests mock or bypass the real async bodies.
- **Impact / possible consequences:** Production-preferred DB path is the least-tested code; closed-loop exceptions indicate pool connections outliving test (and potentially runtime) loops; three persistence mechanisms multiply failure modes (retention/locking/audit-ordering differ per path) — post-shutdown data loss windows, WAL contention, silent divergence between DB and JSONL audit ordering across paths.
- **Risk assessment:** High.
- **Suggested resolution (pending approval):** (a) fix pool lifecycle (close joins worker threads; `pool.close()` in `TradingSystem.shutdown()`), (b) raise additions-module coverage ≥80% or fold into `database.py`, (c) document the dispatch precedence contract.
- **Estimated complexity:** Medium (1 day). **Dependencies:** none. **Priority:** **P1**.

### 🟠 F6-H-04 — CMP strategy core absent (rules / strength / sizing / trailing / VaR / session / Analyzer routing)

- **Issue ID:** F6-H-04 · **Category:** Scope / Architecture · **Severity:** High · **Confidence:** Certain (grep + module inventory, both passes)
- **Evidence:** `src/loats/**` contains 25 `.py` files — **no `rules.py`, no `strength.py`**; grep for `(?i)(ADX|BBANDS|Bollinger|CCI|Hurst|regime)` → zero substantive hits; no `TradeDecision` anywhere; no order-modification counter (rule 7); `trailing_stop_loss` appears only as a stored/passed field (models/DB/payload_builder) — no ratchet engine; `max_position_size=1000` / `max_position_per_symbol=1000` vs CMP rule 11 (5 NIFTY / 3 BANKNIFTY); orchestrator combines (ta+sentiment)/2 — only 2 sources, no opposition gate, no ≥3-source requirement; no VaR computation in `options.py`/`ta.py`.
- **Root cause:** Build proceeded data-layer-first (P0-P3) and stopped partway through P4/P5; the CMP's P2 composite-strength and P4 strategy/risk engines were never started.
- **Impact / possible consequences:** The system cannot trade the CMP strategy; orchestrator "signals" are 2-source averages stored to DB, not gated `TradeDecision`s routed to Analyzer. This is the difference between a research scaffold and the mandated trading system.
- **Risk assessment:** High (scope).
- **Suggested resolution (pending approval):** Execute CMP P4/P5 as a program: `rules.py` gates (IV-rank>40/ADX<25/VIX>15 sell; inverse buy) → `strength.py` ≥3-source composite with opposition gate → 2% fixed-frac cost+margin-aware sizing → monotonic trailing ratchet with SL-M → per-source circuit breakers → session lifecycle (PRE_OPEN→REGULAR→POST_CLOSE) → `TradeDecision` routed to Analyzer; plus rule 7 modification counter and rule 11 position limits (5 NIFTY / 3 BANKNIFTY).
- **Estimated complexity:** High (multi-week). **Dependencies:** F6-H-05 (orchestrator must be correct before building on it). **Priority:** **P1 (program)**.

### 🟠 F6-H-05 — Orchestrator correctness defects (7, all source-verified in both passes)

- **Issue ID:** F6-H-05 · **Category:** Correctness / Reliability · **Severity:** High · **Confidence:** Certain (line-level verification ×2)
- **Evidence (`src/loats/orchestrator.py`):**
  1. `cycle_count` **double-increment**: `:94` (`_execute_trading_cycle`) **and** `:498` (`_record_cycle_time`) — every cycle counted twice; stats (avg at `:499`, periodic log at `:503`) inflated 2×.
  2. Module-level eager settings `:27` `settings = get_settings()` — reintroduces the NEW-L2 anti-pattern; importing `loats.orchestrator` without `OPENALGO_API_KEY` crashes at import.
  3. `:61` `asyncio.create_task(self._run_cycle_loop())` fire-and-forget — no strong reference held; task eligible for GC mid-flight (CPython documented hazard).
  4. `shutdown()` `:521-526` — sets `_shutdown_event` then immediately `await asyncio.wait_for(self._shutdown_event.wait(), timeout=5.0)`: waiting on an already-set flag; the "wait for current cycle" is a no-op.
  5. `:78` — on persistent cycle errors, `alerts.send_system_alert(...)` fires **every 100ms cycle** — alert flood, no backoff.
  6. `:414/418/421` — `funds.utilized_margin / funds.available_margin` → `ZeroDivisionError` when `available_margin == 0` (frozen-funds edge).
  7. `:98` — TA analysis awaited **sequentially before** the 80ms parallel window (`:101-107`); a slow `get_history` (httpx timeout 30s) stalls the loop far beyond the 100ms budget — the CMP latency gate is structurally unachievable under load.
- **Root cause:** New module written to a latency budget without cycle-accounting discipline, lifecycle rigor, or failure-path tests (57% coverage).
- **Impact / possible consequences:** Wrong stats, import fragility, task-loss risk, alert floods, divide-by-zero on a realistic broker state, budget violations.
- **Suggested resolution (pending approval):** Single increment site; lazy settings; hold strong task ref + done-callback; real drain (await the task with timeout after setting the event); alert backoff (e.g. ≥1/min); guard `available_margin == 0`; move TA inside the parallel budget with its own `wait_for`. Add regression tests per defect.
- **Estimated complexity:** Low-Medium (½ day). **Dependencies:** none. **Priority:** **P1**.

---

## 8. Medium Priority Findings (Priority P2)

> Format: ID · Category · Severity · Confidence · Evidence → Resolution · Complexity · Priority. All verified live unless noted.

- **🟡 F6-M-01 — Audit JSONL write skipped under pytest** — Data integrity · Medium · Certain. `database.py:655`: `if os.environ.get("PYTEST_CURRENT_TEST"): skip` — the JSONL-first dual-write guarantee (R5-F-14 fix) is **never exercised by the test suite**; test-runtime behavior diverges from production. → Use tmp-path audit files in tests instead of a prod-path bypass. P2 · Medium.
- **🟡 F6-M-02 — Flaky rate-limiter test** — Testing · Medium · Medium confidence. Investigator pass observed `tests/test_rate_limiter.py::TestAsyncRateLimiter::test_get_wait_time` fail in a full-suite `-x` run yet pass isolated (28/28); Reviewer pass full run: 843/0 — **not reproduced**. Timing/window sensitivity remains the probable cause. → De-flake by injecting a clock; add retry-stable assertions. P2 · Low.
- **🟡 F6-M-03 — Per-module coverage gate is advisory only** — QA process · Medium · Certain. `scripts/check_per_module_coverage.py:104` prints "FAILED (warnings detected)" then `:108/:113` `sys.exit(0)`. Six modules below 80% at HEAD: additions 31%, orchestrator 57%, rate_limiter 72%, strike_selection 74%, scheduler 76%, alerts 79%. → Make warnings exit non-zero or set per-module floors. P2 · Low.
- **🟡 F6-M-04 — Strike-selection cache unbounded** — Performance/memory · Medium · Certain. `strike_selection.py:26` `self._cache: dict[str, list[float]] = {}` keyed by price/strategy (`:66-67`, `:94`); one entry per distinct price tick on a 100ms loop → unbounded growth on a long-running process. → Bound it (`TTLCache(maxsize=…)`); eviction test. P2 · Low.
- **🟡 F6-M-05 — Ruff config weakens the CMP gate** — Code quality · Medium · Certain. `pyproject.toml:101-134`: ignore list disables F401/F841/I001/B007/T201 and more, with duplicated entries (E402, I001, F401, F541 each twice); local `mypy` config relaxed (salvaged only by CI's `--strict` CLI flag). Local bare runs under-report vs CI. → Shrink ignores; align local mypy with CI. P2 · Low.
- **🟡 F6-M-06 — Repo hygiene regression (quantified worse by Reviewer pass)** — Hygiene · Medium · Certain. 302 tracked files; **38 root-level `.py`** debug/verify scaffolds; **38 root-level `.md`** reports (Investigator said "20+"; actual 38). Ruff `exclude` list names 9 of the root scripts (normalizing the mess rather than removing it). Plus untracked junk (`$null`, `[100%]`, `0.21.0`, six `pytest_final*.log`). → `git rm` scaffolds/reports (or move to `docs/audit-history/`), extend `.gitignore`, then shrink the ruff exclude list. P2 · Low.
- **🟡 F6-M-07 — Docker image installs dev extras** — DevOps · Medium · Certain. `Dockerfile:46` `RUN pip install --no-cache-dir -e ".[dev]"` — dev tooling in the production image; editable install in-container; `:43` installs `requirements-core.txt` first (fragile dual-manual). Runtime compose volume `device: ./logs` relative bind (L-R5-12 carried). → Runtime stage: `pip install .`; absolute/env-var bind mounts. P2/P3 · Low.

---

## 9. Low Priority Findings (Priority P3)

- **🟢 F6-L-01 — 34 ambiguous-unicode literals** (RUF001-003: smart quotes/en-dashes in strings/docstrings/comments). Byte-scan (both passes): 0×U+FFFD in `src/` — cosmetic, not corruption (R5-F-21 stays refuted). Fold into F6-C-02 cleanup. P3.
- **🟢 F6-L-02 — Redis ghost import** — `cache.py:23-29` guarded `import redis.asyncio` + unused `REDIS_AVAILABLE` (also a coverage hole at lines 27-29). Dead LITE-drift code. Delete. P3.
- **🟢 F6-L-03 — Empty-match pytest.raises** — `tests/test_orchestrator.py` `pytest.raises(..., match="")` — PytestWarning observed live: "matching against an empty string will *always* pass". Assert a real substring. P3.
- **🟢 F6-L-04 — AsyncMock never awaited** — `tests/test_scheduler_coverage.py` RuntimeWarnings observed live: mock misuse, coroutines dropped. Fix mocks. P3.
- **🟢 F6-L-05 — Duplicate healthcheck definitions** — Dockerfile HEALTHCHECK + compose `healthcheck:` (benign duplication). P3.
- **🟢 F6-L-06 — bloombergquint RSS likely defunct** (carried since FR1) — sentiment source list unvalidated. P3.
- **🟢 F6-L-07 — `ta>=0.11` declared but unused** — custom `ta.py` instead. Adopt or drop the dependency. P3.

---

## 10. Performance Review

| Item | Status | Evidence |
|---|---|---|
| Cycle <100ms | Instrumented, structurally compromised | 100ms budget + adaptive sleep (`orchestrator.py:87-89`); TA runs **outside** the parallel window (F6-H-05.7); unvalidated against live data |
| Strike <5ms | Instrumented | 4ms `wait_for` + 5ms warning + mid-strikes fallback (`orchestrator.py:461-477`); unbounded cache (F6-M-04) |
| Trail <1ms | ❌ N/A | No trailing engine exists |
| SQLite | ✅ | WAL, indexes, thread-local reuse, aiosqlite pool (maxsize=10) |
| Cache | ✅ / 🟡 | In-memory TTLCache, sub-µs hits; `asyncio.Lock` is loop-scope only — not thread-safe if `to_thread` callers ever touch it |
| NumPy vectorization | ✅ | `ta.py` vectorized; supertrend loop inherent (carried, Low) |
| Latency evidence | ❌ | No live ANALYZE round-trip measurements on disk — CMP P1/P5 latency gates remain unvalidated |

## 11. Security Audit

| Check | Status | Evidence |
|---|---|---|
| Bandit | ✅ clean (exit 0, re-run) | — |
| pip-audit | ✅ no known vulns | local pkg skipped |
| Secrets | ✅ | `.env` untracked; no default API key; validator requires value; no SecretStr logging |
| SQLi | ✅ | Parameterized only (raw-SQL hatches removed since FR2) |
| Telegram | ✅ | Admin allow-list; `/kill`,`/resume` gated; `html.escape` applied (incl. former R5-5 gaps — final sweep + `test_html_escaping_final.py`) |
| TLS | ✅ | httpx default verify |
| Idempotency | ✅ client-side | UUID v4 `Idempotency-Key` on all order methods (`openalgo.py:245,605`) + DB duplicate guard; **server-side honoring UNCONFIRMED** (documented at `openalgo.py:23-31`) |
| Kill switch | ✅ | Wired on all order paths + orchestrator loop (`orchestrator.py:532-536`); blocked orders audited |
| **Rate-limit safety** | 🔴 | **Effective 50 OPS (F6-C-01) — the sole critical security-adjacent exposure** |

**Verdict:** No classic security holes. The financial-safety exposure is the OPS cap.

## 12. Scalability Review

Single-process by design (LITE) — horizontal scaling out of scope per CMP. Event loop non-blocking ✅ (async DB wrappers; no F-CONC-1 regression). aiosqlite pool + connection registry improve vertical headroom; tri-modal persistence needs governance (F6-H-03). Cache concurrency: `asyncio.Lock` adequate for the single event loop today; **not thread-safe** for `to_thread` callers — the threading.Lock recommendation from FR5 (R5-F-04) is only half-implemented; commit claim "thread-safe TTLCache" overstated.

## 13. Reliability Review

Kill switch ✅ (orders + orchestrator; audited blocks). Circuit breakers ✅ all paths (fail-fast on POSTs without retry; retry ≤3 on cancel — documented). Retry+backoff+jitter ✅. NSE holiday calendar ✅ (3-year frozenset + 32 tests). Misfire handling ✅ (`misfire_grace_time=30`, `coalesce=True`, `max_instances=1`). Audit JSONL-first ✅ prod / ❌ test-bypass (F6-M-01). Graceful shutdown ✅ main / ❌ orchestrator no-op drain (F6-H-05.4) + aiosqlite loop-closed exceptions (F6-H-03). Alert flood path 🟡 (F6-H-05.5).

## 14. Maintainability Review

Module organization good; `payload_builder` dedupe closed L-R5-10; circuit_breaker/payload_builder/logging at 99-100%. Weakened local ruff/mypy configs mislead developers (F6-M-05). Commit-message discipline rules exist (CONTRIBUTING.md + `commit_message_check.py`) and are **routinely violated by the same commits that added them** (F6-C-02 evidence). Documentation regenerated but some claims again ahead of reality ("89.02% coverage", "Ruff linting passed"). Repo-root artifact sprawl degrades navigability (F6-M-06).

## 15. Code Quality Review (live, HEAD `36d0c52`)

| Gate | Result |
|---|---|
| deps-sync | ✅ PASS |
| ruff check | 🔴 **135 errors** (101 E501, 17 RUF003, 9 RUF001, 8 RUF002) |
| ruff format --check | 🔴 **20 files** |
| isort --check-only | 🔴 **11 files** |
| flake8 (`.flake8`) | ✅ PASS (exit 0) |
| mypy `--strict` | ✅ PASS — "Success: no issues found in 27 source files" |
| bandit | ✅ PASS (exit 0) |
| pip-audit | ✅ PASS |
| pytest | ✅ 843 passed / 0 failed / 9 warnings (116.60s) |
| coverage aggregate | ✅ 80.43% (gate 80) |
| coverage per-module | 🔴 6 modules <80% (advisory gate, F6-M-03) |

## 16. Testing Review

- **843 tests / 0 failed** (Investigator pass observed one flaky failure: `test_get_wait_time` — not reproduced in Reviewer pass; still suspect, F6-M-02).
- Strong: circuit_breaker 99%, payload_builder 100%, loats_logging 100%, models 94%.
- Weak: `database_async_additions` **31%** and `orchestrator` **57%** — the two **newest core modules**; rate_limiter 72% (factory custom-key paths untested: miss lines 429-482 — precisely where F6-C-01 lives).
- Failure-path coverage improved since FR5 (rate-limit regression tests, CB-open, kill-switch, idempotency, NSE holidays ×32, html-escaping final sweep).
- Live-observed warnings: aiosqlite thread `PytestUnhandledThreadExceptionWarning` (F6-H-03); empty-match `pytest.raises` (F6-L-03); `AsyncMock` never awaited ×3 (F6-L-04).
- No load/latency tests against live data; no integration test asserting effective OPS cap (would have caught F6-C-01).
- `tests/scratch/` quarantine exists; 38 root-level `.py` scaffolds remain tracked (F6-M-06).

## 17. DevOps Review

CI (`ci.yml`): fail-fast matrix; deps-sync→ruff→format→isort→flake8→mypy `--strict`→bandit→pip-audit→gitleaks; pytest+cov 80 + per-module (advisory); docker build on PRs; final-status job. `security.yml` weekly (gitleaks/pip-audit/bandit/safety/SBOM — runs not inspected). Docker: non-root ✅, read-only FS ✅, no-new-privileges ✅, resource caps ✅, runtime compose `command: ["python","-m","loats.main"]` ✅ (R5-8 closed), metrics :8001 exposed and started ✅ (R5-2 closed). Gaps: dev-extras in image (F6-M-07), relative bind mounts (L-R5-12), **HEAD would fail CI** (F6-C-02), branch protection not enforced on `main`.

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
| F6-M-05 weakened lint configs | Medium | Certain | Low-Med | 🟡 Medium |
| F6-M-06 repo hygiene (38+38 root artifacts) | Medium | Certain | Low | 🟡 Medium |
| F6-M-07 dev extras in image | Medium | Certain | Low | 🟡 Medium |
| F6-L-01…07 | Low | — | Low | 🟢 Low |

## 19. Technical Debt Assessment (ranked)

1. 🔴 **F6-C-01** — unwired `max_ops` (CMP's loudest non-negotiable); one-line fix + tests.
2. 🔴 **F6-C-02** — 135/20/11 lint-format-import debt + false readiness claims in git history.
3. 🟠 **F6-H-04** — missing strategy core (rules/strength/sizing/trailing/VaR/session/Analyzer routing) — bulk of CMP P4/P5.
4. 🟠 **F6-H-03** — tri-modal persistence + 31%-covered aiosqlite tier.
5. 🟠 **F6-H-05** — orchestrator correctness cluster (7 defects).
6. 🟡 **F6-M-01/02/03/04** — audit test-bypass, flaky test, advisory gate, cache leak.
7. 🟡 **F6-M-05/06/07** — weakened configs, artifact sprawl, image bloat.
8. 🟢 Carried: vollib successor plan, bloombergquint feed, `ta` dep unused, redis ghost import, R5-F-04 half-implementation (asyncio.Lock vs threading.Lock).

## 20. Production Readiness Assessment

**Verdict: NOT READY for live capital. ANALYZE-mode demo only — and current HEAD does not pass its own CI.**

| Gate | Status |
|---|---|
| Import / boot | ✅ (orchestrator import requires env — F6-H-05.2) |
| Tests green | ✅ 843/843 (1 flaky suspect) |
| Coverage ≥80% aggregate | ✅ 80.43% |
| Coverage ≥80% per module | 🔴 6 modules below (advisory gate) |
| Ruff / format / isort | 🔴 🔴 🔴 **FAIL at HEAD** |
| Mypy --strict / flake8 / bandit / pip-audit | ✅ ✅ ✅ ✅ |
| Deps manifests synced | ✅ |
| Kill switch wired + audited | ✅ |
| Idempotency keys | ✅ client-side (broker honoring unconfirmed) |
| Circuit breakers all paths | ✅ |
| **Order-path OPS ≤ self-limit 3** | 🔴 **FAIL — effective 50 (F6-C-01)** |
| Holiday calendar / IST hours | ✅ |
| Strategy engine per CMP | 🔴 Absent |
| TradeDecision → Analyzer routing | 🔴 Absent |
| Docker runtime / non-root / metrics | ✅ |

**Minimum hard requirements before any live deployment:** F6-C-01 (P0) → F6-C-02 (P0) → F6-H-05 (P1) → F6-H-03 (P1) → CMP P4/P5 program (F6-H-04, P1) → F6-M-01/02/03 hardening (P2).

## 21. Prioritized Improvement Roadmap (REVIEW ONLY — awaits USER APPROVAL)

**P0 — immediate (≈90 min total removes both criticals)**
1. **F6-C-01:** default the four limiter factories from `get_settings().max_ops` (class ctors already do — `rate_limiter.py:35/139/254`); add regression test `factory().max_ops == settings.max_ops`; CI assertion cap ≤ 10. (~30 min)
2. **F6-C-02:** `ruff check --fix` + `ruff format` + `isort` + normalize 34 ambiguous-unicode literals; re-run all gates green; enable branch protection requiring CI on `main`; enforce commit-message hook. (~1 h)

**P1 — before any live-order path**
3. **F6-H-05:** orchestrator fixes — single increment site, lazy settings, strong task ref + done-callback, real drain-wait, alert backoff (≥1/min), `available_margin==0` guard, TA inside parallel budget. (~½ day)
4. **F6-H-03:** aiosqlite pool lifecycle (close joins threads, called from `TradingSystem.shutdown()`); raise additions coverage ≥80% or fold into `database.py`; document dispatch precedence. (~1 day)
5. **F6-H-04 (program, CMP P4/P5 order):** `rules.py` gates → `strength.py` ≥3-source composite + opposition gate → 2% fixed-frac sizing (cost+margin aware) → monotonic trailing ratchet with SL-M → per-source breakers → session lifecycle (PRE_OPEN→REGULAR→POST_CLOSE) → `TradeDecision` routed to Analyzer. (multi-week)
6. CMP rule 7: per-order modification counter (≤25). CMP rule 11: position limits 5 NIFTY / 3 BANKNIFTY in Settings + orchestrator risk check (replace the 1000 defaults).

**P2 — robustness/process**
7. **F6-M-01:** tmp-path audit files in tests (kill the `PYTEST_CURRENT_TEST` bypass). **F6-M-02:** de-flake `test_get_wait_time` (inject clock). **F6-M-03:** per-module gate exits non-zero. **F6-M-04:** bound strike cache (`TTLCache`).
8. **F6-M-05:** shrink ruff ignore list (dedupe E402/I001/F401/F541); align local mypy config with CI `--strict`. **F6-M-06:** `git rm` 38 root `.py` + relocate 38 root `.md`; extend `.gitignore`; then shrink ruff `exclude`. **F6-M-07:** runtime Docker stage `pip install .` (no dev extras, no `-e`); absolute bind mounts.

**P3 — hygiene**
9. F6-L-01…07: drop-or-adopt `ta` dep; delete redis ghost import; fix empty-match `pytest.raises`; fix AsyncMock misuse; dedupe healthchecks; validate RSS feeds; complete R5-F-04 (threading.Lock over TTLCache); carried vollib plan.

---

## Appendix A — CMP (LOATS-CMP-13July2026) Conformance Matrix

### A.1 Zero-Assumption Rules (CMP §3 — NON-NEGOTIABLE)

| # | Rule | Evidence | Verdict |
|---|---|---|---|
| 1 | NIFTY lot size 25 | `settings.py:77` `nifty_lot_size=25` | ✅ |
| 2 | No 500ms resting time | No resting logic exists | ✅ (N/A) |
| 3 | Algo ID tagging broker's job; strategy field audit-only | No tag synthesis in payloads | ✅ |
| 4 | **OPS threshold 10; self-limit ≤3** | `settings.py:82` max_ops=3 **unwired**; factories hard-code 50 (`rate_limiter.py:355+`); call sites bare (`openalgo.py:799,876`); probe 50/100 | 🔴 **VIOLATED (F6-C-01)** |
| 5 | Paper trading = Analyzer Mode | `openalgo_mode="ANALYZE"` default (`settings.py:63-65`) | ✅ |
| 6 | Bot-logic trailing SL + SL-M | SL_M enum ✅; trailing field stored/passed only — no ratchet | 🟠 Partial |
| 7 | Order modification limit 25/order | No modification counter (grep-verified) | 🔴 Not implemented |
| 8 | `as_of_date` explicit; never `date.today()` | Zero `date.today(` matches ✅; zero `as_of_date` usage — convention absent | 🟡 Half |
| 9 | py_vollib; newspaper4k; VADER ±0.05 | vollib (documented successor) + newspaper4k + `sentiment_threshold=0.05` | 🟡 Documented deviation |
| 10 | India VIX external input only | No VIX usage at all | 🟡 N/A — unimplemented |
| 11 | Position limits 5 NIFTY / 3 BANKNIFTY | `max_position_size=1000`, `max_position_per_symbol=1000` (`settings.py:88-96`); orchestrator checks vs 1000 (`orchestrator.py:404`) | 🔴 **VIOLATED (200×)** |
| 12 | Trailing = monotonic ratchet; SL-M | SL-M ✅; ratchet engine absent | 🟠 Partial |

### A.2 Phases (CMP §5)

| Phase | CMP gate | Verdict |
|---|---|---|
| P0 Scaffolding+compliance (3d) | ruff/mypy/bandit clean, tests pass | ✅ Done at FR5; **red again today (F6-C-02)** |
| P1 OpenAlgo data layer (1wk) | live ANALYZE round trip | ✅ Client+SQLite+Greeks; live round-trip latency unvalidated |
| P2 TA/VA + Strength (1.5wk) | periods 9/21/50/200, BBANDS 20, CCI 20, regime Hurst+ADX, composite strength | 🟠 ~60% — RSI/MACD/ATR/Supertrend/VWAP/CMF only; **grep-verified: NO ADX, NO BBANDS, NO CCI, NO Hurst, NO regime, no strength module** |
| P3 Sentiment Lite (1wk) | scores ∈ [-1,+1] | ✅ VADER ±0.05 |
| P4 Strategy + Risk (2wk) | rules, strike, 2% sizing, trailing ratchet, VaR, kill switch, backtest sanity | 🟠 ~40% — strike ✅, kill switch ✅, margin check ✅; **no rules/sizing/trailing/VaR/backtest** |
| P5 Orchestrator + Analyzer (1wk) | 3 decision gates (\|score\|>0.6, no opposition>0.4, ≥3 sources), per-source breakers, session lifecycle, ALL decisions → Analyzer, 2-wk forward test | 🟠 ~50% — 0.6 threshold ✅; opposition/≥3-source ❌ (2-source average); per-source breakers ❌ (global only); session lifecycle ❌; **no TradeDecision, no Analyzer routing**; forward test: no evidence |

### A.3 SEBI card & verification (CMP §6/§7)

Audit 7-yr ✅ (`retention_days=2555`); SHA-256 append-only ✅; JSONL-first dual-write ✅ prod / ❌ test-bypass. Verification gates: CI is a superset of the CMP list ✅ — **red at HEAD**. Latency gates instrumented ✅ / live-validated ❌.

### A.4 Structure & hygiene (CMP §4/§8)

Structure deviates (flat `src/loats/` vs prescribed packages) with functional equivalents for strike/orchestrator/kill-switch/audit; missing: `connectors/`, `strategy/rules`, `risk/manager`, `strength`. Secrets hygiene ✅ (`.env` untracked, secrets contained). Compact-repo spirit 🔴 (302 tracked; 38 root `.py` + 38 root `.md`).

**Conformance bottom line: NO — not strict.** LITE philosophy, audit architecture, and data/TA/sentiment layers conform; the trading-strategy core does not exist, and the non-negotiable OPS self-limit is configured-but-unwired at 50.

---

## Appendix B — Investigator (FR6) ↔ Reviewer (FR6-R) Disposition — all findings independently re-verified live

| FR6 finding | Reviewer verdict | Evidence delta |
|---|---|---|
| F6-C-01 | ✅ **Confirmed** | Probe reproduced exactly (identity True; 50; 3; 50/100; 50/100). Root cause refined: class ctors already default from settings — factories override with 50 |
| F6-C-02 | ✅ **Confirmed** | Identical counts: ruff 135 (101/17/9/8), format 20, isort 11 (file list captured) |
| F6-H-03 | ✅ **Confirmed** | 31% coverage reproduced; aiosqlite thread warnings reproduced in live pytest run |
| F6-H-04 | ✅ **Confirmed** | Module inventory (25 files; no rules/strength) + grep absences reproduced |
| F6-H-05 (×7) | ✅ **Confirmed** | All seven line-verified: `:27` eager settings, `:61` fire-and-forget, `:78` alert flood, `:94+498` double increment, `:414/418/421` ZeroDivision, `:521-526` no-op drain wait, `:98` TA outside window |
| F6-M-01 | ✅ Confirmed | `database.py:655` |
| F6-M-02 | 🟡 Confirmed-suspect | Investigator saw 1 failure; Reviewer full run 843/0 — intermittent, consistent with timing sensitivity |
| F6-M-03 | ✅ Confirmed | `check_per_module_coverage.py:104→108/113` exit(0) after "FAILED (warnings detected)" |
| F6-M-04 | ✅ Confirmed | `strike_selection.py:26/66-67/94` plain dict |
| F6-M-05 | ✅ Confirmed | `pyproject.toml:101-134` ignore list w/ duplicates |
| F6-M-06 | ✅ Confirmed, **worse** | 302 tracked; root `.py` = 38; root `.md` = **38** (Investigator said "20+") |
| F6-M-07 | ✅ Confirmed | `Dockerfile:43,46` |
| F6-L-01…07 | ✅ Confirmed (L-03/L-04 reproduced live in pytest warnings) | — |

**Zero refutations. Zero material contradictions. One quantification update (M-06) and one root-cause refinement (C-01).** The Investigator's FR6 report stands as accurate; this consolidated report is the authoritative final deliverable of the 15Aug2026 review chain.

---

## Appendix C — Verification commands (re-runnable, evidence basis)

```powershell
$py = '.\LOATS13July2026\Scripts\python.exe'

# State
git rev-parse HEAD            # 36d0c529e122088d5a65c384ab042dbb5c9897d4
git status --short            # clean (untracked reports only)

# Gates (memory: run in clean venv; flake8 reads .flake8)
& $py scripts\check_deps_sync.py                                  # PASS
& $py -m ruff check src/ tests/ scripts/ --config pyproject.toml --statistics   # FAIL 135
& $py -m ruff format --check src/ tests/ scripts/                 # FAIL 20 files
& $py -m isort --check-only src/ tests/ scripts/ --settings-path pyproject.toml # FAIL 11 files
& $py -m flake8 src/ tests/ scripts/                              # PASS
& $py -m mypy src/ --strict --config-file pyproject.toml          # PASS (27 files)
& $py -m bandit -r src/ -c pyproject.toml -q                      # PASS
& $py -m pytest tests/ --cov=src --cov-branch --cov-fail-under=80 -q
#   → 843 passed, 9 warnings, 116.60s; coverage 80.43%

# F6-C-01 reproduction (probe run in both passes; see §6 for verbatim output)
$env:OPENALGO_API_KEY='probe'
# probe asserts: singleton identity True; effective max_ops 50; settings.max_ops 3;
#                50/100 order acquires; 50/100 smart acquires
```

## Appendix D — "Not enough evidence" disclosures

- **OpenAlgo server-side honoring of `Idempotency-Key`:** not verifiable from the repository (client documents it as unconfirmed, `openalgo.py:23-31`).
- **Live ANALYZE-mode round-trip latency (CMP P1 gate) and the P5 "2-week forward test":** no run-log evidence exists on disk.
- **`security.yml` weekly workflow results:** workflow file present; execution results not inspected in either pass.
- **Coverage drift:** Investigator recorded 80.41%; Reviewer recorded 80.43% on the same HEAD — timing jitter in branch coverage; both clear the 80% gate.

---

**End of Final Consolidated Report (FR-FINAL). REVIEW-ONLY deliverable — no code modified. All recommendations require explicit USER APPROVAL before implementation.**

**Summary:** The FR6 Investigator's audit is accurate — every finding re-confirmed live by the independent Reviewer pass, zero refutations. The build is **not strictly per the CMP**: effective order-path cap is 50 OPS against a mandated self-limit of 3 (`Settings.max_ops=3` dead — one-line fix since the limiter classes already default from settings); HEAD fails ruff/format/isort while commits claim readiness; and the CMP strategy core (rules/strength/sizing/trailing/VaR/session/Analyzer routing) does not exist. ~90 minutes of approved work (F6-C-01 + F6-C-02) removes both criticals; the strategy core is a multi-week program. **NOT READY for live capital. ANALYZE-mode demo only.**

*Note: this report file itself is an untracked repo-root artifact — relocate to `docs/audit-history/` or remove before any release, per F6-M-06.*
