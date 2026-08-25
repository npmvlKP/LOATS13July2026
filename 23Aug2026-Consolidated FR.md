# LOATS13July2026 — Consolidated Forensic Engineering Report (Review #7 Chain — Investigator FR7 + Reviewer FR7-R, Final)

**Date:** 2026-08-23
**Project:** LOATS13July2026 — Lite OpenAlgo Trading System (Indian equities/options research; OpenAlgo broker API; Telegram alerts; APScheduler + orchestrator analysis pipeline)
**Repository:** https://github.com/npmvlKP/LOATS13July2026.git (HEAD `163cdf9a674a6e9c4d373d2d2481f3f47cd52cf3`, 2026-08-23; working tree clean apart from untracked review artifacts)
**Python:** 3.12.7 — clean venv `G:\.OA\LOATS-13July2026\LOATS13July2026\LOATS13July2026\`
**Master plan audited against:** `LOATS-CMP-13July2026.txt` (Compact Master Plan, "LITE" edition)
**Mode:** REVIEW ONLY — no code modified, no patches generated, no refactors performed, no destructive operations executed. Every recommendation is conditional on explicit USER APPROVAL.

**This document consolidates two same-day reports into one authoritative deliverable:**

| Role | Source report | Status after consolidation |
|---|---|---|
| Investigator (FR7) — CMP Conformance Re-Audit | `23Aug2026-Investigator FR.md` | Archived to `docs/audit-history/` |
| Reviewer (FR7-R) — Verification & Final Consolidation | `23Aug2026-Reviewer FR.md` | Archived to `docs/audit-history/` |
| **Consolidated (this file)** | `23Aug2026-Consolidated FR.md` | **Authoritative final deliverable of the 23Aug2026 review chain** |

**Consolidation rule:** where the two reports differ, the Reviewer's re-verified values are authoritative (the Reviewer independently re-verified every FR7 finding live with zero refutations). Material deltas: one EXTENSION (F7-C-02 diversity gate — 4 sources required, not 3), two CORRECTIONS (pip-audit installed 2.10.1; eager settings ×11 not ×10), two QUANTIFICATIONS (docs/audit-history = 75 files; coverage 76.38% vs 76.36% — timing jitter). All Investigator-unique evidence is preserved.

**Reviewers (Senior Engineering Review Board):** Principal Software Architect · Senior Python Engineer · Senior Code Reviewer · Production Debugging Engineer · Performance Optimization Engineer · Scalability Engineer · Security Auditor · DevOps & Infrastructure Engineer · QA / Test Architect · Reliability Engineer (SRE) · Technical Lead · Systems Design Reviewer

---

## 0. Sequential Remediation TODO Checklist (P0 → P3)

> **This is the actionable processing order for the next build wave.** Ordered by dependency + severity. Each item references its finding registry entry (§7) for full evidence and acceptance criteria. All items await explicit USER APPROVAL before implementation.

### P0 — Restore truthful gates + a living strategy chain (≈2–3 days)

- [ ] **TODO-1 (F7-C-01a):** Delete `src/__init__.py` (the mypy module-collision breaker). Re-run `mypy src/ --strict` → must exit 0.
- [ ] **TODO-2 (F7-C-01b):** Relocate the 8 stray `src/*.py` files (`cmp.py`, `probe_rate_limiter.py`, `test_cmp.py`, `test_cmp_conformance.py`, `test_cmp_ops_threshold.py`, `utils.py`, `var_engine.py`) → `scripts/` or `tests/` as appropriate; delete the 7 empty CMP-named package shells (`connectors/`, `risk/`, `risk/manager/`, `strategy/`, `strategy/rules/`).
- [ ] **TODO-3 (F7-C-01c):** Raise coverage on `trailing_stop` (11%), `trade_decision` (30%), `backtest_sanity` (0%), orchestrator CMP body `:638-737`, `options.py` (66%) → aggregate ≥80% + per-module ≥80% (or documented exclusion for intentionally dormant modules).
- [ ] **TODO-4 (F7-C-01d):** Re-run pip-audit in a network-enabled environment (tool IS installed: `pip_audit 2.10.1`; sandbox blocked the vulnerability-DB fetch, not absence).
- [ ] **TODO-5 (F7-C-01e):** **Enable branch protection requiring CI on `main`** — fourth consecutive review requesting it; its absence is the single enabling condition for the 4-review misleading-commit pattern.
- [ ] **TODO-6 (F7-C-01f):** Enforce the existing `commit_message_check.py` hook.
- [ ] **TODO-7 (F7-C-02a):** Tag the three signal producers with **enum-valid** `StrengthSource` identities (`"source": "ta"`, `"source": "sentiment"`, `"source": "price_action"`) instead of `"orchestrator"` ×3.
- [ ] **TODO-8 (F7-C-02b):** Deliver **≥4 real enum-valued producers** (4th candidate: `volatility` — nearly free from existing ATR/Hurst data) **OR** recalibrate `diversity_threshold` to 3/7 ≈ 0.43 with a documented ADR reconciling it with CMP's "≥3 sources" wording. NOTE: the Investigator's original 3-producer fix is **mathematically insufficient** — 3 enum sources = 0.4286 < 0.5 (Reviewer empirical probe).
- [ ] **TODO-9 (F7-C-02c):** Make unknown `source` strings a loud validation error instead of silent collapse to `TECHNICAL_ANALYSIS` (`strength/__init__.py:361-362`).
- [ ] **TODO-10 (F7-C-02d):** End-to-end test driving the **REAL** orchestrator signal path (not fabricated Signal objects) through `create_trade_decision`.
- [ ] **TODO-11 (F7-C-02e):** Elevate the insufficient-signals `logger.debug` (`orchestrator.py:631`) to INFO/WARNING with a periodic counter.

### P1 — Make the CMP chain real (≈1 week)

- [ ] **TODO-12 (F7-H-02):** Wire India VIX (cached OpenAlgo quote for the India VIX symbol) into `set_vix_level()` on the market-data task. Fail-safe must be **symmetric** (no-feed ⇒ gate fails BOTH directions, or explicitly-unknown + logged). Currently 18.5 fallback permanently blocks BUY / vacuously passes SELL.
- [ ] **TODO-13 (F7-H-01):** Replace the simulated routing stub (`trade_decision.py:231-279`) with real Analyzer routing via `AsyncOpenAlgoClient` (ANALYZE mode) + persist every TradeDecision and routing result to SQLite/JSONL audit. Integration test must assert an external side-effect (HTTP call or audit row). Default `analyzer_routing_enabled=True` currently fabricates success.
- [ ] **TODO-14 (F7-H-04):** Trailing-stop runtime driver: per open position → fetch price → ratchet update → Rule-7-gated SL-M modification (ANALYZE mode). Persist ratchet events to audit. Depends: TODO-3 (tests), TODO-16.
- [ ] **TODO-15 (F7-H-03):** ≥80% per-module tests on the strategy layer: ratchet monotonicity property tests (never loosen), sizing edges (zero funds, huge spread), VaR vs known distributions, routing failure paths. Re-run `check_per_module_coverage.py` as blocking CI step.

### P2 — CMP-correct values + robustness (≈2–3 days)

- [ ] **TODO-16 (F7-M-01):** BUY gate IV-rank `< 30` per CMP (currently `< 60` at `rules.py:256-257`). 1 line + tests.
- [ ] **TODO-17 (F7-M-02):** `max_modifications = 25` (currently 30, mislabeled "CMP Rule 7: ≤30"); wire the setting into the `openalgo.py:514` gate; persist counters (SQLite); fail-closed (currently fail-open `rules.py:419-420`, volatile across restarts).
- [ ] **TODO-18 (F7-M-03):** Lazy settings accessor across **11** modules (incl. `trailing_stop.py:28`, missed in the Investigator count of 10).
- [ ] **TODO-19 (F7-M-04):** Retire the legacy 2-source combiner OR convert it into the tagged producer set (feeds TODO-7/8). Two engines, two thresholds (0.6 legacy vs 0.5 CMP), one DB.
- [ ] **TODO-20 (F7-M-05):** Delete the `PYTEST_CURRENT_TEST` JSONL bypass (`database.py:774`); tmp-path audit files in tests instead. Commit `a03047e` claimed this was fixed — it was not.
- [ ] **TODO-21 (F7-M-06/08):** Untrack root junk (`$null`, `[100%]`, `0.21.0`, ~14 lint/security report JSONs); prune stale `docs/audit-history/` + `reports/` content (343 tracked total).

### P3 — Hygiene

- [ ] **TODO-22 (F7-L-01):** Shrink the 20-rule ruff ignore list (incl. F401, I001, E402, PGH003).
- [ ] **TODO-23 (F7-L-03):** Remove dead strength-source weights (`FUNDAMENTAL 0.1`, `MACHINE_LEARNING 0.3`, `OPTIONS_FLOW 0.2`) or keep with documented pending-producer rationale.
- [ ] **TODO-24 (F7-L-04):** Verify `check_per_module_coverage.py` final `exit(0)` semantics at `:113`.
- [ ] **TODO-25 (F7-L-05):** Collect P1 live ANALYZE round-trip latency + P5 2-week forward-test run-log evidence.
- [ ] **TODO-26 (F7-L-06):** Fold `backtest_sanity.py` driver work into TODO-14 (zero production callers today).
- [ ] **TODO-27 (carried):** vollib → py_vollib successor plan; `ta` dependency drop-or-adopt; bound the decision queue (`trade_decision.py:324-332`) once routing is real.

---

## 1. Executive Summary

### 1.1 Verdict

**The FR7 Investigator's audit is accurate: every finding re-confirmed live by the Reviewer, zero refutations.** The project is closer to the CMP than at any prior review — the OPS self-limit ≤3 is now **empirically enforced** (verified twice: 3/10 acquires, singleton, settings-wired), all seven FR6 orchestrator defects are fixed (line-verified 7/7), the CMP strategy modules exist and are import-wired, Rule 11 position limits are correct, Docker is hardened.

**The project is still NOT built strictly per `LOATS-CMP-13July2026.txt`, and HEAD fails its own CI.** The CMP decision chain cannot execute in production (F7-C-02 — and needs **4** sources, not 3), Analyzer routing is a simulation (F7-H-01), the VIX risk gate is inert and structurally anti-BUY (F7-H-02), and two CI gates are red (mypy exit 2; coverage 76.38% < 80) while recent commits claim "fully complies" (`98e7d89`), "~100% phase completion" (`92b99f2`), and "READY FOR LIVE DEPLOYMENT" (`471762d`) — the **fourth consecutive review** documenting the misleading-commit pathology (R5b-F-NEW-1 → F6-C-02 → F7-C-01).

**NOT READY for live capital. ANALYZE-mode demo only — and current HEAD does not pass its own CI.**

The 47-commit wave since FR6 delivered real, verifiable substance: OPS ≤3 enforced (F6-C-01 CLOSED), seven orchestrator defects fixed (F6-H-05 CLOSED), strategy layer built (`rules.py`, `sizing.py`, `strength/`, `trailing_stop.py`, `trade_decision.py`, `backtest_sanity.py`, `trading_strategy/core.py`), position limits 5/3 configured (Rule 11), session lifecycle exists, Docker hardened. But the wave also delivered its own undoing: the two most important claims of the build wave are not true in the operational sense — (1) the CMP strategy chain is **unreachable at runtime** (every signal's source is `"orchestrator"` against a ≥3-unique-source gate, plus a stacked diversity gate requiring ≥4-of-7 enum sources), and (2) Analyzer routing is a **stub** (docstring: *"In production, this would send to actual Analyzer service. For now, we simulate."*).

### 1.2 Investigator → Reviewer disposition (the substance of the consolidation)

| # | Delta | Impact |
|---|---|---|
| 1 | **F7-C-02 EXTENDED (material):** the source gate is **two stacked gates**, not one. After the ≥3-unique-source check, a **diversity gate** requires `diversity_score ≥ 0.5` where `score = unique_enum_sources / 7` (`strength/__init__.py:396`, `:365`) — i.e., **≥4 distinct `StrengthSource`-enum-valued producers are mathematically required**. Verified empirically: `ta+sentiment+price_action` (3 valid sources) → **REJECTED** (0.4286 < 0.5); adding a 4th → **PASSED** (0.5714). The Investigator's proposed fix ("tag 3 producers, add a third real source") is **insufficient** — three tagged producers still fail. Worse: the CMP's own P5 wording is "≥3 sources", so the implemented gate is *stricter than the plan* — a strict-direction conformance deviation that makes the plan's own success criterion unattainable. Also: unrecognized source strings silently collapse to `TECHNICAL_ANALYSIS` (`:361-362`). | Fix scope grows: 4 real enum-valued producers, or recalibrate diversity to 3/7≈0.43 with documented ADR |
| 2 | **F7-C-01 / F7-L-02 pip-audit sub-claim CORRECTED:** Investigator stated pip-audit "NOT RUNNABLE — module not installed in venv". **Wrong:** `pip show` proves `pip_audit 2.10.1` IS installed; the Investigator's invocation `python -m pip-audit` (hyphen) is invalid module syntax — correct forms are `python -m pip_audit` or `pip-audit.exe` (which CI uses correctly: `ci.yml:48 pip-audit --format=json`). The gate remains **unverifiable in the review sandbox** (two execution attempts timed out on vulnerability-DB network fetch: 420 s and 240 s), so "not enough evidence" stands — but for network egress, not absence. | Gate honesty preserved; environment bug in the Investigator's methodology documented |
| 3 | **F7-M-03 quantified 11, not 10:** eager module-level `settings = get_settings()` at `alerts.py:37`, `backtest_sanity.py:26`, `main.py:19`, `rules.py:22`, `scheduler.py:36`, `sentiment.py:22`, `sizing.py:21`, `strength/__init__.py:20`, `trade_decision.py:26`, `trading_strategy/core.py:23`, **and `trailing_stop.py:28`** (missed by the Investigator). | +1 module to the lazy-settings fix |
| 4 | **F7-M-08 quantification:** `docs/audit-history/` = **75** tracked files (Investigator said 76); `reports/` = 42 ✓; total 343 ✓; root carries 47 tracked files including junk artifacts `$null`, `[100%]`, `0.21.0` and ~14 lint/security report JSONs. | Trivial; junk-at-root detail added |
| 5 | **F7-H-01 aggravating detail:** `analyzer_routing_enabled = True` by default (`trade_decision.py:46`) — the simulation is **active by default**, fabricating `{"status": "success", "analyzer_response": {"status": "QUEUED_FOR_ANALYSIS"}}` for any decision that reaches it. | Default-on fabrication, not opt-in |
| 6 | Coverage 76.38% (Reviewer) vs 76.36% (Investigator) — timing jitter in branch coverage; both FAIL the 80 gate. Verdict unchanged. | None |

### 1.3 CMP demand vs build reality (verified live, both passes)

| CMP requirement | State at HEAD `163cdf9` | Verdict |
|---|---|---|
| LITE: zero services, pip-only | SQLite WAL + JSONL audit; custom `threading.Lock` TTL cache (redis ghost import deleted); stdlib metrics | ✅ Conformant |
| Pipeline: Sentiment → TA/VA → **Strength** → **Rules** → Strike → Risk → Orchestrator | All modules exist and are import-wired (`orchestrator.py:21,25` → `trade_decision.py:20-23` → rules/sizing/strength/trailing_stop) | ✅ Structurally present — **but dead at runtime (F7-C-02)** |
| **Rule 4: OPS threshold 10; self-limit ≤3** | **EMPIRICALLY ENFORCED (×2)**: probe — singleton identity True, `effective max_ops: 3`, `settings.max_ops: 3`, **3/10 acquires**; factories default from settings (`rate_limiter.py:36,149,180`); call sites bare (`openalgo.py:820,897`) | ✅ **FIXED (F6-C-01 closed)** |
| Rule 7: modification limit **25**/order | `openalgo.py:514` enforces 25 (hard-coded); **but `settings.py:99` declares `max_modifications=30` labeled "CMP Rule 7: ≤30"** — wrong value, dead knob; counters in-memory, fail-open, reset on restart | 🟠 Partial + mislabeled |
| Rule 8: `as_of_date`; never `date.today()` | Zero `date.today(` matches; `as_of_date` convention still absent | 🟡 Half (unchanged) |
| Rule 9: py_vollib; newspaper4k; VADER ±0.05 | `vollib` (documented successor, `VOLLIB_MIGRATION_PLAN.md`); newspaper4k ✅; `sentiment_threshold=0.05` ✅ | 🟡 Documented deviation (carried) |
| Rule 10: India VIX = external input | `rules_engine.set_vix_level()` exists — **zero production callers** (grep: definition only). Gate always uses fallback **18.5** | 🔴 **Input never wired (F7-H-02)** |
| Rule 11: position limits 5 NIFTY / 3 BANKNIFTY | `max_nifty_positions=5`, `max_banknifty_positions=3` (`settings.py:104-109`); legacy 1000s retained as generic fallback | ✅ Fixed |
| Rule 12: trailing = monotonic ratchet; SL-M | `trailing_stop.py` (545 stmts) exists; `initialize_trailing_stop` called once at decision time (`trade_decision.py:145`); **ratchet update/monitor logic has zero production callers** — SL-M never moves after entry | 🟠 Partial (engine dormant) |
| P2 gate: BBANDS 20, CCI 20, Hurst, ADX, regime | `calculate_bbands` / `calculate_cci` / `calculate_hurst_exponent` / `calculate_adx_standalone` (`ta.py:385,414,447,546`) + strength integration | ✅ Implemented |
| P2 strength composite | `strength/` package with per-source weights, opposition gate 0.4, min_sources 3 | ✅ Implemented — **starved of sources at runtime** |
| P4: rules gates (IV-rank/ADX/VIX), 2% sizing, trailing, VaR, backtest | Rules gates real (`rules.py:205-286`); 2% fixed-frac sizing ✅; VaR ✅ (`options.calculate_portfolio_var`); **BUY gate uses IV-rank < 60, CMP says < 30** (`rules.py:256-257`); `backtest_sanity.py` **0% covered, never invoked in prod** | 🟠 Partial (F7-M-01, F7-H-03) |
| P5: 3 gates, per-source breakers, session lifecycle, ALL decisions → Analyzer, 2-wk forward test | Session lifecycle ✅ (`rules.py:37-62`); 0.6/0.4 thresholds ✅; **routing simulated**; per-source breakers ❌ (global only); forward test: no evidence | 🟠 ~50% (F7-C-02, F7-H-01) |
| Verification gates (ruff, mypy --strict, bandit, cov ≥80, pip-audit) | ruff/format/isort/flake8/bandit/deps-sync ✅ — **mypy 🔴 (collision), coverage 🔴 76.38%, pip-audit unverifiable (offline)** | 🔴 Gates red at HEAD (F7-C-01) |
| Repo structure per CMP §4 | Flat `src/loats/` retained; `connectors/`, `risk/manager/`, `strategy/rules/` created as **empty ~159–175-byte `__init__.py` shells** (structure theater); 8 stray files directly in `src/` incl. `src/__init__.py` (the mypy breaker), `test_cmp*.py`, probe scripts | 🟠 Deviation + F7-M-06 |
| Git hygiene (compact repo) | Root nominally cleaned (3 `.md` + 47 tracked root files incl. junk), `.env` untracked ✅ — but repo **grew** 302 → **343 tracked** (75 `docs/audit-history/` + 42 `reports/ai-generated/`) | 🟡 Mixed |

Full clause-by-clause matrix: **Appendix A**. FR6 disposition: **Appendix B.1**. Investigator↔Reviewer disposition: **Appendix B.2**.

### 1.4 Scorecard across the review chain

| Dimension | FR5 (08Aug) | FR6 (15Aug) | FR7 Investigator (23Aug) | **FR7-R Reviewer (23Aug)** | Trend |
|---|---|---|---|---|---|
| Tests | 640/0 | 843/0 | 1123/0 | **1123/0 (re-run)** | ✅ Up |
| Coverage (aggregate) | 80.10% | 80.43% | 76.36% FAIL | **76.38% FAIL (re-run)** | 🔴 Regressed |
| Ruff | 0 | 135 | 0 | **0 (re-run)** | ✅ Recovered |
| Ruff format / isort | clean | 20/11 dirty | clean | **clean/clean (re-run)** | ✅ Recovered |
| Mypy `--strict` | 0 | 0 | FAIL exit 2 | **FAIL exit 2 (verbatim re-run)** | 🔴 Regressed |
| Flake8 / bandit / deps-sync | mixed | clean | clean | **clean (re-run)** | ✅ Held |
| pip-audit | pass | pass | "not installed" | **installed 2.10.1; network-blocked here — unverifiable** | 🟡 Unverifiable (corrected) |
| Order-path OPS ≤3 | broken | singleton @ 50 | 3 enforced | **3 enforced (probe: 3/10, 3/10)** | ✅ **FIXED** |
| Orchestrator defects (7) | n/a | 7 open | 0 open | **0 open (7/7 line-verified)** | ✅ Fixed |
| CMP strategy core | absent | absent | present, runtime-dead | **present, runtime-dead — and needs 4 sources, not 3** | 🟠 Half-real |
| Commit claims vs reality | false | false | false (4th) | **false (4th) — re-verified in `git log`** | 🔴 4th review running |

### 1.5 The three things that matter most

1. **F7-C-01 (Critical, process):** HEAD fails its own CI — mypy (exit 2, `src/__init__.py` module collision, checking aborted before a single file was type-checked) and coverage (76.38% < 80; the new sizing/trailing/VaR/routing/backtest code is the least-tested in the repo). The final commits of the wave claim full compliance within hours of pushing a red tree. Branch protection on `main` — recommended in FR5 §21, FR6 §21, FR7 §21 — has never been enabled. That omission is the single enabling condition for four consecutive reviews of false readiness claims.
2. **F7-C-02 + extension (Critical, conformance):** the CMP decision chain is doubly unreachable — production supplies **1** unique source against a ≥3 gate, and even a correctly tagged 3-producer fix fails the diversity gate (needs **≥4** of 7 enum sources). Every conformance test passes only because tests fabricate signal sets production cannot produce — sets that even a correct 3-producer fix cannot produce. "CMP strategy implemented" is true of the code path, not of the system.
3. **F7-H-01 + F7-H-02 (High, conformance):** even if the source gates were satisfied, decisions would terminate in a **default-on simulated routing stub** (log + `sleep(0.1)` + fabricated success), and the only decisions that could ever pass gating are **SELL** — the unwired VIX fallback of 18.5 fails BUY's `vix < 15` unconditionally while vacuously passing SELL's `vix > 15`.

---

## 2. Architecture Overview

```
src/loats/                              # importable package (hatch wheel target)
├── __init__.py                         # PEP 562 lazy settings; initialize_system()
├── initialization.py / loats_logging.py# logging bootstrap; structlog-first
├── metrics.py                          # stdlib ThreadingHTTPServer :8001 + in-memory stats
├── config/                             # lazy Settings; __all__=[Settings, get_settings]
├── models.py                           # Pydantic v2; TradeDecision, VaRResult, SL_M, session enum
├── database.py                         # sqlite3 WAL + JSONL-first audit + aiosqlite pool (79% cov)
├── database_async_additions.py         # monkey-patch true-async aiosqlite methods (71% cov)
├── openalgo.py                         # sync+async clients; kill switch; CB all paths; Idempotency-Key;
│                                       #   Rule 7 gate (hard-coded 25); OPS limiters (3, settings-wired)
├── alerts.py                           # Telegram v20+; admin allow-list; html.escape (79% cov)
├── scheduler.py                        # APScheduler; IST + NSE holidays; shared db singleton (76%)
├── orchestrator.py                     # 100ms cycle; 80ms parallel window; legacy 2-source signals
│                                       #   (source="orchestrator" ×3) + _execute_cmp_strategy() (67%)
├── rules.py                            # session lifecycle; IV-rank/ADX/VIX gates; mod counters (92%)
├── strength/                           # per-source weights; composite; opposition 0.4;
│                                       #   min_sources=3 + diversity≥0.5 (needs 4 enum sources!)
├── sizing.py                           # 2% fixed-fractional, cost+margin aware (96%)
├── trailing_stop.py                    # ratchet engine — 545 lines, 11% cov, NEVER driven (F7-H-04)
├── trade_decision.py                   # CMP decision workflow; SIMULATED routing, default-on (30%)
├── backtest_sanity.py                  # walk-forward sanity — 0% cov, zero callers (F7-L-06)
├── trading_strategy/core.py            # strategy facade (91%)
├── performance_analyzer.py             # benchmark harness (97%)
├── strike_selection.py / sentiment.py / ta.py / options.py
└── utils/                              # cache (threading.Lock TTL), circuit_breaker (99%),
                                        #   connection_pool (91%), payload_builder (100%),
                                        #   rate_limiter (settings-wired, 84%), resilience, retry

src/                                    # ⚠ STRAY LAYER (8 files): __init__.py (mypy breaker),
                                        #   cmp.py, probe_rate_limiter.py, test_cmp*.py ×3,
                                        #   utils.py, var_engine.py (counts in coverage at 100%)
src/loats/{connectors,risk,risk/manager,strategy,strategy/rules}/
                                        # ⚠ 7 EMPTY SHELLS (~159-175 bytes each) — CMP §4 structure theater
```

**Runtime lifecycle:** `TradingSystem.initialize()` → metrics server → `db.async_initialize()` + audit verify → alerts/scheduler init → `start()` → `alerts.start()` + `scheduler.start()` + `start_orchestrator()` → cycle loop ~100 ms: parallel (TA ‖ sentiment ‖ market-data, 80 ms `wait_for` + cancel-on-timeout) → legacy `_execute_signal_generation()` → `_execute_risk_management()` → `_execute_cmp_strategy()` (session-gated) → shutdown: real drain (`await asyncio.wait_for(self._cycle_task, 5.0)` + cancel) → scheduler → alerts → `async_close_all()`.

**Architectural deltas since FR6 (verified both passes):**
1. **Strategy layer added** (rules/strength/sizing/trailing_stop/trade_decision/backtest_sanity/trading_strategy) — import-wired into orchestrator and openalgo (Rule 7 gate).
2. **Two parallel signal engines coexist**: the legacy 2-source combiner (`orchestrator.py:187`, threshold 0.6, stores to DB every cycle) and the CMP chain (`:609+`, reads those same signals, threshold 0.5 at `trade_decision.py:88`, requires ≥3 unique + ≥4-for-diversity sources). The legacy path feeds the DB the CMP path then starves on (F7-M-04 + F7-C-02).
3. **Rate limiter settings-wired** — class ctors and factories default from `settings.max_ops` (F6-C-01 closed; re-verified empirically).
4. **Cache rewritten** as `threading.Lock` TTL cache (redis ghost import gone — R5-F-04/F6-L-02 fully closed).
5. **Docker hardened** — multi-stage, `pip install --no-deps .`, non-root `USER loats` (F6-M-07 closed).
6. **`src/__init__.py` + stray `src/*.py` introduced** — direct cause of the mypy gate failure (F7-C-01a).

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
 LEGACY PATH (every cycle)          CMP PATH (session-gated, every cycle)
 _execute_signal_generation         _execute_cmp_strategy (:609)
   ta signal   source="orchestrator"  db.async_get_latest_signals (≤10, 5 min window)
   sentiment   source="orchestrator"  → GATE 1: ≥3 UNIQUE sources ──► ALWAYS FAILS (1 unique)
   combined    source="orchestrator"  → GATE 2: diversity ≥ 0.5 (4-of-7 enum) ──► UNREACHABLE
   → stored to DB                      └── (would be: gating → 2% sizing → trailing init → VaR
                                          → TradeDecision → route_to_analyzer — SIMULATED:
                     │                    log + sleep(0.1) + fabricated success, default-ON)
                     ▼
 AsyncOpenAlgoClient — kill switch → OPS limiter (3/s, EMPIRICAL 3/10) → Rule 7 gate
                      (≤25, hard-coded; settings knob=30 DEAD) → CB fail-fast
                      → Idempotency-Key (UUID v4; cancel/modify keyed by order_id;
                        place/smart by payload digest) → OpenAlgo REST (ANALYZE default)
                     │
                     ▼
 db.async_* (aiosqlite pool → to_thread fallback) → SQLite WAL + JSONL audit
   (JSONL-first canonical SHA-256; ⚠ PYTEST_CURRENT_TEST bypass still at database.py:774)
```

**Order path (financial-critical), verified line-level by both passes:** `place_order` → `_async_check_kill_switch()` (`openalgo.py:818`) → `get_order_rate_limiter().acquire()` (`:820`, defaults from settings = 3/s) → CB open-check (fail-fast, no retry) → `_request(..., idempotency_key=...)` → `Idempotency-Key` header + DB duplicate-order guard. `modify_order` → `_check_kill_switch()` (`:509`) → `rules_engine.check_modification_limit(order_id, limit=25)` (`:514`, hard-coded; the `Settings.max_modifications=30` knob is never read — and is wrong anyway, CMP Rule 7 = 25). Kill-switch blocks audited.

**Async boundary:** orchestrator/scheduler/alerts on one event loop; aiosqlite pool spans worker threads; legacy sqlite3 via `to_thread`; RSS/newspaper via `to_thread`+`gather`. TA analysis now runs **inside** the 80 ms parallel window (`orchestrator.py:167-184`) with cancel-on-timeout — F6-H-05.7 fixed, re-verified.

---

## 4. Dependency Overview

| Dependency | pyproject | requirements-core | Verdict |
|---|---|---|---|
| Core set (httpx, pydantic(-settings), APScheduler, numpy, pandas, scipy, vaderSentiment, feedparser, newspaper4k, structlog, python-telegram-bot, python-dotenv, aiosqlite, lxml, lxml-html-clean, cryptography, cachetools-replacement) | ✅ | ✅ | ✅ Synced — `check_deps_sync.py` PASS (gate-enforced, re-run) |
| `vollib>=1.0.11` | ✅ | ✅ | 🟡 CMP rule 9 says `py_vollib`; documented successor deviation (VOLLIB_MIGRATION_PLAN.md) — carried; mypy override `module = "vollib.*"` |
| `ta` dependency | ✅ | ✅ | 🟡 Still declared; custom `ta.py` used — drop or adopt (carried) |
| **pip-audit** (dev extra) | ✅ | ✅ | 🟡 **Installed (`pip_audit` 2.10.1) — Investigator's "not installed" corrected.** Execution in the review sandbox blocked by network egress to the vulnerability DB (two attempts timed out: 420 s, 240 s). CI invocation is correct (`ci.yml:48 pip-audit --format=json`). Gate state at HEAD: **not enough evidence** (offline), not "absent". |

External integrations: OpenAlgo REST, Telegram Bot API, RSS feeds (bloombergquint still unvalidated — carried). **India VIX has no feed** (F7-H-02).

---

## 5. Module-by-Module Review

Coverage from the Reviewer's live run (1123 tests, branch coverage on; Investigator table identical):

| Module | Stmts | Cover | Verdict | Key notes |
|---|---|---|---|---|
| `utils/payload_builder.py` | 54 | **100%** | ✅ | Shared order-payload builder |
| `src/var_engine.py` ⚠ stray | 196 | **100%** | 🟠 | Fully covered — but lives OUTSIDE the package, directly in `src/` (F7-M-06) |
| `loats_logging.py` / `initialization.py` | 20/6 | **100%** | ✅ | structlog-first |
| `performance_analyzer.py` | 180 | 97% | ✅ | NEW benchmark harness |
| `config/settings.py` | 85 | 96% | ✅ | `max_ops=3` wired; **`max_modifications=30` mislabeled "CMP Rule 7: ≤30"** (CMP=25) |
| `sizing.py` | 127 | 96% | ✅ | NEW; 2% fixed-fractional |
| `strength/config.py` | 45 | 96% | 🟠 | NEW |
| `trading_strategy/core.py` | 160 | 91% | ✅ | NEW facade |
| `models.py` | 262 | 92% | ✅ | TradeDecision/VaRResult/session enums |
| `utils/circuit_breaker.py` | 141 | 99% | ✅ | |
| `rules.py` | 169 | 92% | ✅ | NEW; gates + session + counters; **BUY IV-rank 60 vs CMP 30; VIX fallback 18.5** |
| `sentiment.py` | 109 | 93% | ✅ | VADER ±0.05 |
| `utils/connection_pool.py` | 74 | 91% | ✅ | Pool lifecycle fixed (F6-H-03 partly closed) |
| `utils/resilience.py` / `utils/retry.py` | 87/89 | 89/87% | ✅ | |
| `main.py` | 124 | 88% | ✅ | Metrics + orchestrator wired |
| `ta.py` | 401 | 87% | ✅ | ADX/BBANDS/CCI/Hurst added — CMP P2 indicator set complete |
| `openalgo.py` | 411 | 87% | ✅ | Order paths covered; Rule 7 gate; settings-wired OPS limiters |
| `utils/rate_limiter.py` | 212 | 84% | ✅ | **3 OPS enforced** (empirical ×2) |
| `utils/cache.py` | 269 | 85% | ✅ | threading.Lock TTL cache; thread-safe |
| `metrics.py` | 183 | 85% | ✅ | |
| `database.py` | 597 | 79% | 🟠 | **PYTEST_CURRENT_TEST JSONL bypass at :774 (F7-M-05)** |
| `alerts.py` | 478 | 79% | 🟠 | Broad except paths untested |
| `scheduler.py` | 371 | 76% | 🟠 | Job-error paths untested |
| `database_async_additions.py` | 225 | 71% | 🟠 | Up from 31% (FR6); pool lifecycle fixed; teardown warnings gone; still <80% |
| `orchestrator.py` | 457 | 67% | 🔴 | **CMP strategy body `:638-737` in the missing list** — the runtime-dead path is also the untested path |
| `options.py` | 343 | 66% | 🔴 | **Regression 90% → 66%** precisely when VaR became a pre-trade input (F7-M-07); miss `:736-989` VaR/Greeks edges |
| `strike_selection.py` | 211 | 66% | 🟠 | |
| `trade_decision.py` | 127 | **30%** | 🔴 | NEW; routing/queue/persist bodies untested (miss `:70-200, 238-274, 283-382` — `:238-274` is the stub itself) |
| `backtest_sanity.py` | 159 | **0%** | 🔴 | NEW; CMP P4 gate module — zero tests, zero production callers |
| `trailing_stop.py` | 270 | **11%** | 🔴 | NEW; ratchet math untested (miss `:73-545`) AND never invoked at runtime |

---

## 6. Evidence Basis (both passes, all live, clean venv, HEAD `163cdf9`)

`git rev-parse/log/status` (47 commits since FR6 HEAD `36d0c52`, 2026-08-16 → 08-23); `check_deps_sync.py` **PASS**; `ruff check` **PASS (0 errors)**; `ruff format --check` **PASS (132 files)**; `isort --check-only` **PASS**; `flake8` **PASS**; `mypy src/ --strict` **FAIL — exit 2**, verbatim: `"Source file found twice under different module names: 'src.loats.utils.rate_limiter' and 'loats.utils.rate_limiter' … errors prevented further checking"`; `bandit` **PASS**; `pip-audit` — installed (`pip_audit` 2.10.1), execution blocked by sandbox network egress (Investigator's `-m pip-audit` invocation was invalid — corrected); `pytest` **1123 passed / 0 failed / 1 warning** — Investigator run 160.35 s / coverage 76.36%, Reviewer run 141.16 s / coverage 76.38% (timing jitter) — **both `--cov-fail-under=80` GATE FAIL (exit 1)**; per-module coverage table (live); empirical rate-limiter probe — **singleton identity True; effective max_ops 3; settings.max_ops 3; 3/10 order and 3/10 smart acquires in a 10-acquire burst** (identical in both passes); **empirical strength-gate probe (Reviewer, new)** — production-shaped signals (3× `source="orchestrator"`) → `(False, insufficient_unique_sources, available=1/required=3)`; three enum-valid distinct sources (`ta`/`sentiment`/`price_action`) → `(False, insufficient_source_diversity, 0.4286 < 0.5)`; four enum-valid sources → `(True, source_validation_passed, 0.5714)`; source reads of `orchestrator.py`, `strength/__init__.py`, `trade_decision.py`, `rules.py`, `trailing_stop.py` (import graph), `rate_limiter.py`, `config/settings.py`, `openalgo.py` (modification/rate-limit call sites), `database.py:774`, `Dockerfile`, `pyproject.toml`, `ci.yml:47-48`, `scripts/check_per_module_coverage.py`; greps (`set_vix_level` callers = definition only; `update_trailing_stop` callers = zero; `backtest_sanity` external importers = zero; `date.today(` = zero; `PYTEST_CURRENT_TEST`; eager `settings = get_settings()` = **11 modules**); git inventory (343 tracked; 47 root files incl. tracked junk `$null`, `[100%]`, `0.21.0`; `docs/audit-history/` = **75**; `reports/ai-generated/` = 42; 8 stray files in `src/`; 7 empty shells ~159–175 bytes).

---

## 7. Unified Findings Registry

> Each entry: **I** = Investigator original evidence, **R** = Reviewer re-verification/extension (authoritative on conflict), **Fix** = consolidated resolution (maps to §0 TODOs).

### 7.1 Critical (P0)

#### 🔴 F7-C-01 — HEAD fails its own CI: mypy gate broken (module collision) + coverage gate broken (76.38% < 80)

- **Category:** Process / Quality Gates · **Severity:** Critical (blocks merge; contradicts commit claims) · **Confidence:** Certain (live runs, both passes)
- **Owning specialists:** Technical Lead, QA / Test Architect, DevOps & Infrastructure Engineer
- **I:** `mypy src/ --strict` → exit 2, module-name collision, checking aborted. Root cause new this wave: `src/__init__.py` (added by the "missing package structure" commit `98e7d89`) makes `src` a package; mypy crawls `src/` computing `src.loats.*` names while imports resolve as `loats.*` → collision. Zero type errors reported — the gate fails before checking. `pytest --cov-fail-under=80` → 1123/0, coverage 76.36% → FAIL. Aggregate dropped 80.43% → 76.36% because new strategy modules arrived untested. pip-audit reported "NOT RUNNABLE — module not installed". Contrast (same tree): deps-sync ✅, ruff ✅, ruff-format ✅ (132 files), isort ✅, flake8 ✅, bandit ✅. Commit claims contradicted: `98e7d89` (08-22) "System now fully complies with CMP Rule 4 … All existing tests continue to pass"; `92b99f2` "~100% phase completion"; `471762d` (08-20) "Production Deployment Approved … Final Status: ✅ READY FOR LIVE DEPLOYMENT"; `163cdf9` (08-23, HEAD) verification claims with no gate re-run; `042a006` "Proper enforcement of 30 modification limit (CMP Rule 7)" — the wrong value codified. **Fourth consecutive review** of the misleading-commit pathology (R5b-F-NEW-1 → F6-C-02 → F7-C-01).
- **R:** Confirmed verbatim — same mypy error reproduced; coverage 76.38% (jitter, same verdict). Sinks: `trailing_stop` 11%, `backtest_sanity` 0%, `trade_decision` 30%, orchestrator CMP body untested, `options.py` 90→66%. **pip-audit sub-claim CORRECTED:** `pip show pip_audit` → 2.10.1 installed; Investigator's `python -m pip-audit` (hyphen) is invalid module syntax; correct forms (`pip-audit.exe` / `python -m pip_audit`) hang in the sandbox on vulnerability-DB network fetch (420 s and 240 s timeouts). Conclusion unchanged — gate state not verifiable here — but the reason is network egress, not absence. CI (`ci.yml:47-48`) invokes it correctly.
- **Root cause:** Structural change (`src/__init__.py` + strays) shipped without re-running CI; large new modules shipped untested; **branch protection on `main` still absent** (recommended FR5 §21, FR6 §21, FR7 §21 — never actioned).
- **Impact:** No merge or release possible from HEAD; `git log` gives false confidence for a fourth consecutive review; untested financial-decision code (sizing/trailing/VaR/routing) described as verified.
- **Fix (TODO-1…6):** (a) delete `src/__init__.py`; (b) relocate the 8 stray `src/*.py` files; (c) raise coverage on the sink modules to ≥80%; (d) re-run pip-audit in a network-enabled environment; (e) **enable branch protection requiring CI on `main`** — fourth time asking; (f) enforce `commit_message_check.py`.
- **Complexity:** Low-Medium (a+b ≈ 1 day; c+d+e+f ≈ 30 min + coverage work 1-2 days). **Priority:** **P0**.

#### 🔴 F7-C-02 — CMP strategy chain is unreachable at runtime: 1 unique source vs ≥3 gate — AND the stacked diversity gate requires FOUR enum sources, not three (Reviewer extension)

- **Category:** CMP Conformance / Correctness (financial decisioning) · **Severity:** Critical · **Confidence:** Certain (line-level evidence + logic trace + empirical probes both passes)
- **Owning specialists:** Principal Software Architect, Production Debugging Engineer, Systems Design Reviewer, QA / Test Architect
- **I (Gate 1 — unique sources):** Signal creation sites (all three, `orchestrator.py`): `:271` TA signal `metadata={"scan_type": "ta", "source": "orchestrator"}`; `:336-340` sentiment `metadata={"scan_type": "sentiment", "source": "orchestrator", ...}`; `:478-484` combined `metadata={"scan_type": "combined", "source": "orchestrator", ...}`. Validation (`strength/__init__.py:379-390`): `source_set = {signal.metadata.get("source", "unknown")}` → `if len(source_set) < self.min_sources` (min_sources = 3, `:50`) → reject `"insufficient_unique_sources"`. Production `source_set` = `{"orchestrator"}` → size 1 < 3 → **`create_trade_decision` returns `(None, rejected)` at Step 1 (`trade_decision.py:73-82`) on every cycle, forever.** The downstream chain (composite strength → gating rules → position limits → 2% sizing → trailing init → VaR → TradeDecision → routing) executes **only in tests**, which fabricate signals with varied `source` strings. Commit `98e7d89` claims the "Trading-Strategy Core" is "Properly Wired"; `92b99f2` claims "~100% phase completion" for P4/P5 — the wiring is import-level only. The strength engine even defines weights for `PRICE_ACTION`, `VOLATILITY`, `FUNDAMENTAL`, `MACHINE_LEARNING`, `OPTIONS_FLOW` (`:41-47`) — **no production producer exists for any of them**. Orchestrator logs the rejection only at `logger.debug` (`:631`) — the core mandate silently no-ops.
- **R (Gate 2 — diversity, discovered + driven empirically this pass):** even with distinct sources, validation then requires `diversity_score ≥ 0.5` (`strength/__init__.py:396`), where `diversity_score = unique_enum_sources / 7` (`:365`; `StrengthSource` has 7 members, `:23-32`). **≥0.5 × 7 = 3.5 → 4 distinct enum-valued sources are mathematically required.** Live probes:
  - 3× `source="orchestrator"` (production-shaped) → `(False, {'reason': 'insufficient_unique_sources', 'required': 3, 'available': 1, 'sources': ['orchestrator']})`
  - `ta + sentiment + price_action` (3 valid enum sources) → `(False, insufficient_source_diversity, 0.4286 < 0.5)`
  - `ta + sentiment + price_action + volatility` (4 sources) → `(True, source_validation_passed, 0.5714)`
  - Unrecognized source strings silently collapse to `TECHNICAL_ANALYSIS` (`:361-362`) — a mis-tagged producer would silently masquerade as TA and lower the count.
  - **Consequence for the fix:** the Investigator's remediation ("tag producers with real source identities; implement a third real producer") is **insufficient** — three tagged producers still fail Gate 2.
  - **Consequence for conformance:** CMP P5 wording is "≥3 sources". The implementation demands 4 — a strict-direction deviation from the plan. A system that can never satisfy its own plan's success criterion is non-conformant even when the deviation is "safer".
- **Root cause:** Gate implemented over `metadata["source"]` while producers were never taught to identify themselves; diversity threshold (0.5 of 7) chosen without arithmetic against the plan's 3-source requirement.
- **Impact:** The system cannot produce a TradeDecision in production. All conformance evidence is test-fabricated — and, per the extension, fabricated sets that even a correct 3-producer fix cannot produce (diversity gate needs 4). Any operator reading the CMP Conformance Report or commit log believes a decisioning engine is running.
- **Fix (TODO-7…11):** (a) tag producers with enum-valid identities (`ta`, `sentiment`, `price_action`, `volatility`…); (b) build **at least 4** real producers OR recalibrate `diversity_threshold` to 3/7 ≈ 0.43 with a documented ADR reconciling it with CMP "≥3 sources"; (c) end-to-end test driving the REAL orchestrator signal path (not fabricated Signals) through `create_trade_decision`; (d) elevate the insufficient-signals log to INFO/WARNING with a periodic counter; (e) reject unknown source strings loudly instead of silently mapping them to TA.
- **Complexity:** Low-Medium (tagging: hours; 4th producer or threshold ADR: 1-2 days; e2e test: ½ day). **Priority:** **P0**.

### 7.2 High (P1)

#### 🟠 F7-H-01 — Analyzer routing is a default-on simulated stub; no decision ever leaves the process

- **Category:** CMP Conformance (P5) / Financial Safety · **Severity:** High · **Confidence:** Certain
- **I:** `trade_decision.py:231-270` — docstring: *"In production, this would send to actual Analyzer service. For now, we simulate the routing and return success."* Body: builds `to_analyzer_payload()`, **logs it, `await asyncio.sleep(0.1)`, returns fabricated** `{"status": "success", "analyzer_response": {"status": "QUEUED_FOR_ANALYSIS", ...}}`. No OpenAlgo call, no DB persist of the decision, no Analyzer-mode submission. Commit `98e7d89` claims "`TradeDecisionEngine.route_to_analyzer()` handles API integration" — **false**.
- **R:** Confirmed + aggravated: `self.analyzer_routing_enabled = True` (`:46`) — the simulation is **active by default**; any decision reaching it receives a fabricated success. Coverage shows `:238-274` (the stub itself) in the missing list — even the simulation is untested.
- **Root cause:** Interface completed ahead of integration; commit message described the interface as the integration.
- **Impact:** Even with F7-C-02 fixed, decisions terminate in a log line. CMP P5 "route ALL TradeDecisions to Analyzer" unmet; the P5 2-week forward test cannot begin.
- **Fix (TODO-13):** Route via `AsyncOpenAlgoClient` in ANALYZE mode + persist every TradeDecision and routing result to SQLite/JSONL audit; integration test asserting an external side-effect (HTTP call or audit row).
- **Complexity:** Medium (4-8 h). **Dependencies:** F7-C-02. **Priority:** **P1**.

#### 🟠 F7-H-02 — India VIX input never wired; 18.5 fallback permanently blocks BUY and vacuously passes SELL (CMP Rule 10)

- **Category:** CMP Conformance / Correctness · **Severity:** High · **Confidence:** Certain
- **I:** `rules.py:187-196` — `get_vix_level()` returns `self._vix_level` or **18.5 "Neutral default"**. `set_vix_level()` (`:198`) has **zero production callers** (repo-wide grep: definition and docstring only). Gating (`:231-259`): SELL requires `vix > 15` → 18.5 always passes; BUY requires `vix < 15` → 18.5 always fails.
- **R:** Confirmed — `set_vix_level` grep: definition only; BUY `vix<15` unreachable at 18.5; SELL `vix>15` vacuous.
- **Root cause:** Rule 10 ("India VIX = external input, never derived") honored in shape (setter exists, nothing derives VIX) but never connected to a feed; the "neutral" default was chosen without checking its gate consequences.
- **Impact:** A so-called neutral default is structurally **anti-BUY / pro-SELL-eligible**. If F7-C-02 were fixed, the system could only ever emit SELL decisions. VIX-based risk-off protection (VIX>15) is decorative — a risk control that cannot detect risk-off.
- **Fix (TODO-12):** Wire an external VIX source (cached OpenAlgo quote for the India VIX symbol) into `set_vix_level()` on the market-data task; fail-safe must be **symmetric** (no-feed ⇒ gate fails for BOTH directions, or explicitly-unknown and logged).
- **Complexity:** Low-Medium (2-4 h). **Priority:** **P1**.

#### 🟠 F7-H-03 — New financial-decision modules shipped untested; aggregate coverage below gate

- **Category:** Testing / Risk · **Severity:** High · **Confidence:** Certain (live coverage table, both passes)
- **I:** `trailing_stop.py` 11% (229/270 missed — the ratchet math itself), `backtest_sanity.py` 0% (159 missed — the CMP P4 gate module, also zero production callers), `trade_decision.py` 30% (routing/queue/persistence bodies), `orchestrator.py` 67% with the CMP body `:638-737` untested, `options.py` regressed 90% → 66%. Aggregate 76.36% → CI gate fail. The per-module advisory gate (F6-M-03, hardened to exit non-zero per `check_per_module_coverage.py:19,64,74,108`) was evidently not run before the final commits.
- **R:** Confirmed — live coverage table reproduced identically (76.38% aggregate).
- **Impact:** The code that decides position size, stops, and VaR — the highest-consequence logic in the repo — has the least test evidence. Untested AND runtime-dead (F7-C-02): defects there are invisible twice over.
- **Fix (TODO-15):** ≥80% per module: ratchet monotonicity property tests (never loosen), sizing edges (zero funds, huge spread), VaR vs known distributions, routing failure paths; re-run `check_per_module_coverage.py` as a blocking CI step.
- **Complexity:** Medium (1-2 days). **Priority:** **P1**.

#### 🟠 F7-H-04 — Trailing ratchet never operates at runtime: initialized once, never updated (CMP Rule 12 partial)

- **Category:** CMP Conformance / Reliability · **Severity:** High · **Confidence:** Certain
- **I:** `trailing_stop_engine` has exactly one production call site — `trade_decision.py:145` `initialize_trailing_stop(...)` (config creation). No scheduler job, no orchestrator step, no order path calls any update/monitor method (repo grep). The monotonic-ratchet enforcement (the actual Rule 12 behavior — SL-M ratchets as price moves) is never executed. 11% coverage matches: only init is exercised.
- **R:** Confirmed — `update_trailing_stop` (`:149`) and every monitor method: zero callers, re-grepped this pass.
- **Root cause:** Rule 12 implemented as a library, not as a subsystem — no runtime driver.
- **Impact:** Stops configured at entry never trail. For a bot-logic trailing system (bracket orders disabled per Rule 6), the core exit-protection mechanism does not exist operationally.
- **Fix (TODO-14):** Runtime driver (orchestrator risk step or APScheduler job): per open position → fetch price → ratchet update → Rule-7-gated SL-M modification in ANALYZE mode; persist ratchet events to audit.
- **Complexity:** Medium (1 day). **Dependencies:** F7-H-03 (tests), F7-M-02 (counter persistence). **Priority:** **P1**.

### 7.3 Medium (P2)

- **🟡 F7-M-01 — BUY gate IV-rank threshold 60 vs CMP 30** — CMP §strategy/rules: "buy: IV rank<30". `rules.py:256-257`: `# BUY rules: IV-rank < 60 …` / `iv_pass = iv_rank < 60`. SELL gate (>40) matches CMP. The BUY band is **double the plan** — buys would be permitted in IV regimes the plan classifies as sell-side. Re-verified line-level by both passes. Fix (TODO-16): `< 30` + tests. Certain; 1 line. P2.
- **🟡 F7-M-02 — `Settings.max_modifications = 30` labeled "CMP Rule 7: ≤30"; CMP mandates 25; live gate hard-codes 25** — `settings.py:99-101` vs `openalgo.py:514` (`limit=25`). Knob dead AND wrong; commit `042a006` codifies the wrong value in history. Counters: in-memory dict (`rules.py:396-400`), lazily created, **fail-open** (`:419-420` `return True  # No tracking yet`), reset on restart — a restart resets an order's modification budget; not audit-grade. Fix (TODO-17): 25, wire the setting, persist counters (SQLite), fail-closed. Re-verified. P2 · Medium.
- **🟡 F7-M-03 — Eager module-level `settings = get_settings()` in ELEVEN modules (Reviewer: 11; Investigator: 10)** — `alerts.py:37`, `backtest_sanity.py:26`, `main.py:19`, `rules.py:22`, `scheduler.py:36`, `sentiment.py:22`, `sizing.py:21`, `strength/__init__.py:20`, `trade_decision.py:26`, `trading_strategy/core.py:23`, **`trailing_stop.py:28` (missed by Investigator)**. Import crashes without `OPENALGO_API_KEY`; the F6-H-05.2 anti-pattern was fixed in `orchestrator.py` (lazy, `:162-165`) and simultaneously reintroduced everywhere else. Fix (TODO-18): lazy accessor per module. P2 · Low.
- **🟡 F7-M-04 — Dual signal engines: legacy 2-source combiner still runs every cycle alongside the CMP chain** — `orchestrator.py:187` `_execute_signal_generation()` (2-source average, 0.6/0.4 thresholds, `:441-486`) writes the very DB signals the CMP path then rejects. Two thresholds coexist (legacy 0.6; trade_decision 0.5 minimum at `trade_decision.py:88`). Confusion risk: which engine is "the" signal source of record? Fix (TODO-19): retire the legacy combiner or convert it into the TA+sentiment producers **with real source tags** (feeds F7-C-02). P2.
- **🟡 F7-M-05 — Audit JSONL write still bypassed under pytest despite fix claim (F6-M-01 NOT fixed)** — `database.py:774`: `if os.environ.get("PYTEST_CURRENT_TEST"):` skip. Commit `a03047e` claims "F6-M-01 … kill the PYTEST_CURRENT_TEST bypass" — the bypass is still present at HEAD. The JSONL-first dual-write guarantee remains untested by the suite; test-runtime behavior diverges from production. Fix (TODO-20): tmp-path audit files; delete the bypass. P2 · Low.
- **🟡 F7-M-06 — `src/` stray layer (8 tracked files outside the package) + 7 empty package shells** — `src/{__init__.py (the mypy breaker — root cause of F7-C-01a), cmp.py, probe_rate_limiter.py, test_cmp.py, test_cmp_conformance.py, test_cmp_ops_threshold.py, utils.py, var_engine.py}`; shells at `src/loats/{connectors,risk,risk/manager,strategy,strategy/rules}` (~159-175 bytes each) — CMP §4 structure theater without content (`var_engine.py` even counts in coverage at 100%). Fix (TODO-2): move scripts to `scripts/`/`tests/`, delete `src/__init__.py`, delete or populate shells. Verified by directory listing both passes. P2 · Low.
- **🟡 F7-M-07 — `options.py` coverage regression 90% → 66%** — VaR/Greeks edge paths (`:736-989`) untested precisely when VaR became a pre-trade input (`trade_decision.py` imports `calculate_portfolio_var`). Fold into F7-H-03. P2.
- **🟡 F7-M-08 — Repo 343 tracked files (302 → 343) while "cleanup" was claimed; root junk persists** — `docs/audit-history/` = **75** (Reviewer count; Investigator said 76) incl. `debug_*.py`, `fix_test_imports.py`, `test_redis_cache.py` (old scripts with `src.loats` imports); `reports/ai-generated/` = 42; root = 47 tracked files (3 `.md` nominally, plus junk `$null`, `[100%]`, `0.21.0` and ~14 lint/security report JSONs). Hygiene moved, not removed; ruff/mypy must exclude or carry them. Fix (TODO-21). P2 · Low.

### 7.4 Low (P3)

- **🟢 F7-L-01 — Ruff ignore list still broad (20 rules)** — `pyproject.toml [tool.ruff.lint] ignore` includes `F401` (unused imports unchecked), `I001`, `E402`, `PTH123`, `N803/N806`, `INP001`, `PGH003` (blanket type: ignore), `RUF005/006/012/015/022/059`. Commit `a03047e` claimed F6-M-05 "shrink ruff ignore list"; the list is still large (duplicates removed at best). Local runs under-report vs a strict config. P3.
- **🟢 F7-L-02 — pip-audit verification (CORRECTED)** — installed (2.10.1); Investigator's invocation was wrong (`-m pip-audit`); execution blocked only by sandbox network. Re-verify in a network-enabled env. P3-adjacent-to-P0 for gate honesty.
- **🟢 F7-L-03 — Strength weights defined for sources that do not exist** — `FUNDAMENTAL 0.1`, `MACHINE_LEARNING 0.3`, `OPTIONS_FLOW 0.2` (`strength/__init__.py:45-47`) — dead configuration until producers exist (ties into F7-C-02). P3.
- **🟢 F7-L-04 — `check_per_module_coverage.py` exit semantics** — hardened since FR6 (multiple `exit(1)` paths `:19,64,74,108`); final success-path `exit(0)` at `:113` not fully traced — mark for verification when F7-H-03 lands. Likely improved. P3.
- **🟢 F7-L-05 — CMP phase-gate evidence absent** — P1 "live ANALYZE round trip" and P5 "2-wk forward test": no run-log evidence on disk (carried since FR6). P3.
- **🟢 F7-L-06 — `backtest_sanity.py` zero production callers** — the CMP P4 exit gate ("backtest sanity on /history data") is a module without a driver. P3 (fold into F7-H-03/H-04 driver work — TODO-14/26).
- **🟢 F7-L-07 — Pytest emits 1 benign warning** (down from 9 at FR6 — aiosqlite teardown and mock-misuse warnings resolved). P3.

---

## 8. Specialist Reviews

### 8.1 Performance

| Item | Status | Evidence |
|---|---|---|
| Cycle <100 ms | Instrumented; structure sound | TA inside 80 ms parallel window with `wait_for` + cancel (`orchestrator.py:167-184`, re-verified); adaptive sleep; unvalidated against live data |
| Strike <5 ms | Instrumented | 4 ms `wait_for` + fallback; strike cache bounded (TTLCache — F6-M-04 fix held) |
| Trail <1 ms | ❌ N/A at runtime | Ratchet never driven (F7-H-04) |
| SQLite | ✅ | WAL, indexes, thread-local reuse, aiosqlite pool |
| Cache | ✅ | Custom `threading.Lock` TTL cache; sub-µs hits; thread-safe (R5-F-04 fully closed) |
| NumPy | ✅ | Vectorized indicators incl. new ADX/BBANDS/CCI/Hurst |
| Latency evidence | ❌ | No live ANALYZE round-trip measurements on disk (carried) |

### 8.2 Security

| Check | Status | Evidence |
|---|---|---|
| Bandit | ✅ exit 0 (re-run) | — |
| Secrets | ✅ | `.env` untracked; validator requires key; no SecretStr logging |
| SQLi | ✅ | Parameterized only |
| Telegram | ✅ | Admin allow-list; `/kill` `/resume` gated; html.escape |
| TLS | ✅ | httpx default verify |
| Idempotency | ✅ client-side | UUID v4 keys + DB dup guard (cancel/modify keyed by order_id; place/smart by payload digest); broker honoring UNCONFIRMED (documented, `openalgo.py:23-31`) — carried |
| Kill switch | ✅ | All order paths + orchestrator loop; audited blocks |
| **OPS limit ≤3** | ✅ **FIXED (re-verified ×2)** | Probe: singleton True; max_ops 3 = settings 3; **3/10 + 3/10** acquires |
| **VIX risk-off gate** | 🔴 decorative | Never fed; 18.5 fallback biases decisions (F7-H-02) — a risk-off control that cannot detect risk-off |
| pip-audit | 🟡 installed / unverifiable here | Network-blocked sandbox; CI invocation correct |

**Verdict:** Classic perimeter clean. The CMP's loudest non-negotiable (OPS ≤3) is finally, empirically enforced — the first review in the chain to confirm it, now confirmed twice. Remaining exposure is decision-integrity (VIX decorative, fail-open modification counters, default-on fabricated routing success), not perimeter.

### 8.3 Scalability

Single-process by design (LITE) — horizontal scaling out of CMP scope. Event loop non-blocking ✅ (parallel window + `to_thread`). aiosqlite pool lifecycle fixed; additions module 71% (up from 31%). Cache thread-safe. **Carried concern (Investigator origin, Reviewer concurred):** the decision queue (`trade_decision_engine.decision_queue`) is unbounded and its processor task is created lazily on first enqueue (`trade_decision.py:324-332`, re-verified) — if enqueues ever outpace the simulated 0.1 s routing, memory grows without bound. Bounded queue or backpressure once routing is real. Low likelihood today (chain is dead upstream — F7-C-02).

### 8.4 Reliability

Kill switch ✅ (orders + orchestrator, audited). Circuit breakers ✅ all paths (no-retry POSTs, retry ≤3 cancel — documented). Retry/backoff/jitter ✅. NSE holiday calendar ✅ (3-year frozenset, 32 tests). Misfire handling ✅. Alert flood ✅ fixed (1/min backoff, `orchestrator.py:140-144`, re-verified). Orchestrator shutdown ✅ real drain (`:836-847`, re-verified). aiosqlite teardown warnings ✅ gone (1 benign warning in 1123-test run). Audit JSONL-first ✅ prod / ❌ test-bypass (F7-M-05). **Open gaps:** VIX risk-off inert (F7-H-02); trailing stops never managed (F7-H-04); modification counters volatile fail-open (F7-M-02); decision queue unbounded (§8.3).

### 8.5 Maintainability

Strategy layer adds clear seams (rules/strength/sizing/trailing/decision) — good. Eroding it: dual signal engines (F7-M-04), empty CMP-named shells + stray `src/` layer (F7-M-06), eager settings ×11 (F7-M-03). Documentation: `VERIFICATION_RESULTS.md` (stale) deleted; `CMP_CONFORMANCE_REPORT.md` at root claims runtime conformance both passes refute empirically — doc claims again ahead of reality. Commit discipline rules exist (`CONTRIBUTING.md`, `commit_message_check.py`) and are violated by the same wave that cites them — 4th consecutive review. Repo: 343 tracked incl. 117 docs/reports files + root junk (F7-M-08).

### 8.6 Code Quality Gates (live, HEAD `163cdf9`, Reviewer re-run)

| Gate | Result |
|---|---|
| deps-sync | ✅ PASS |
| ruff check | ✅ PASS (0 errors; 20-rule ignore list — F7-L-01) |
| ruff format --check | ✅ PASS (132 files) |
| isort --check-only | ✅ PASS |
| flake8 (`.flake8`) | ✅ PASS |
| **mypy `src/ --strict`** | 🔴 **FAIL — exit 2, module collision (`src/__init__.py`), checking aborted** |
| bandit | ✅ PASS |
| pip-audit | 🟡 installed 2.10.1; network-blocked in review sandbox — unverifiable |
| pytest | ✅ 1123/0, 1 warning … but 🔴 **coverage 76.38% < 80 → gate FAIL (exit 1)** |
| per-module ≥80% | 🔴 12+ modules below (incl. 0%, 11%, 30%, 66%×2, 67%) |

### 8.7 Testing

- **1123/1123 passing** — largest, greenest suite in the chain (843 → 1123); warnings 9 → 1. Re-run: identical pass count.
- **The pass is misleading as a conformance signal:** CMP-chain tests fabricate multi-source signal sets production cannot produce (F7-C-02) — and, per the Reviewer extension, sets that even a correct 3-producer fix cannot produce (diversity gate needs 4). The heaviest new logic is the least covered (trailing 11%, backtest 0%, trade_decision 30%, orchestrator CMP body untested, options 66%).
- Strong areas: circuit_breaker 99%, payload_builder 100%, logging 100%, performance_analyzer 97%, sizing 96%, rules 92%, trading_strategy/core 91%.
- Failure-path tests for the legacy stack remain good (rate-limit regression incl. the OPS-cap integration test, CB-open, kill-switch, idempotency, NSE holidays ×32, html-escaping).
- **No end-to-end test drives real orchestrator signal production → decision creation** — the single test gap that would have caught F7-C-02 before this review chain did.
- Audit dual-write still bypassed under pytest (F7-M-05) — the JSONL-first guarantee remains untested.

### 8.8 DevOps

CI (`ci.yml`): fail-fast; deps-sync→ruff→format→isort→flake8→mypy `--strict`→bandit→pip-audit→gitleaks→pytest `--cov-fail-under=80` + per-module; docker build on PRs; final-status. **At HEAD: mypy and coverage jobs RED (F7-C-01).** pip-audit step invocation correct (`pip-audit --format=json`). **Branch protection on `main`: absent** — direct pushes bypass everything; the enabling condition for the 4-review misleading-commit pattern. Docker: multi-stage, `pip install --no-deps .`, non-root `USER loats`, no dev extras ✅ (F6-M-07 closed, re-verified). Runtime compose CMD `-m loats.main` ✅. Metrics :8001 ✅. Health checks ✅. Secrets hygiene ✅.

---

## 9. Risk Matrix

| Finding | Severity | Likelihood | Impact | Risk |
|---|---|---|---|---|
| F7-C-01 gates red at HEAD + false claims (4th review) | Critical | Certain | High (process) | 🔴 Critical |
| F7-C-02 CMP chain dead at runtime — **needs 4 sources** | Critical | Certain | High (mandate no-op) | 🔴 Critical |
| F7-H-01 routing simulated, default-on | High | Certain | High (P5 unmet) | 🟠 High |
| F7-H-02 VIX never wired; biased 18.5 default | High | Certain | Medium-High (BUY structurally blocked; risk-off inert) | 🟠 High |
| F7-H-03 new financial modules untested; cov 76.38% | High | Certain | High | 🟠 High |
| F7-H-04 trailing ratchet never driven | High | Certain | Medium (Rule 12) | 🟠 High |
| F7-M-01 BUY IV-rank 60 vs CMP 30 | Medium | Certain | Medium | 🟡 Medium |
| F7-M-02 mod-limit 30 vs 25; volatile fail-open counters | Medium | Certain | Medium | 🟡 Medium |
| F7-M-03 eager settings ×11 | Medium | Certain | Low-Med | 🟡 Medium |
| F7-M-04 dual signal engines | Medium | Certain | Low-Med | 🟡 Medium |
| F7-M-05 audit test-bypass persists despite claim | Medium | Certain | Medium | 🟡 Medium |
| F7-M-06 src/ stray layer + empty shells | Medium | Certain | Low-Med | 🟡 Medium |
| F7-M-07 options.py 90%→66% | Medium | Certain | Medium | 🟡 Medium |
| F7-M-08 repo 343 files + root junk | Medium | Certain | Low | 🟡 Medium |
| F7-L-01…07 | Low | — | Low | 🟢 Low |

---

## 10. Technical Debt Assessment (ranked)

1. 🔴 **F7-C-02** — source tagging + **4 enum-valued producers (or a documented diversity-threshold ADR recalibrating to the CMP's 3)**; without it the strategy layer is ornamental.
2. 🔴 **F7-C-01** — delete `src/__init__.py`/strays; lift new-module coverage ≥80; **enable branch protection on `main`**; re-run pip-audit online.
3. 🟠 **F7-H-01** — real Analyzer routing + audit-grade decision persistence.
4. 🟠 **F7-H-02** — VIX feed + symmetric fail-safe.
5. 🟠 **F7-H-04** — trailing-stop runtime driver (Rule 12 operational).
6. 🟠 **F7-H-03 / F7-M-07** — tests for sizing/trailing/VaR/routing; options.py recovery to ≥85%.
7. 🟡 **F7-M-01/02** — thresholds to CMP values; counters persisted, fail-closed.
8. 🟡 **F7-M-03/04/05/06/08** — lazy settings ×11, single signal engine, audit dual-write tested, src/ layer cleaned, repo pruned.
9. 🟢 Carried: vollib successor plan, `ta` dep drop-or-adopt, dead strength-source weights, per-module gate exit verification, P1/P5 latency/forward-test evidence, ruff ignore shrink, bounded decision queue.

---

## 11. Production Readiness Assessment

**Verdict: NOT READY for live capital. ANALYZE-mode demo only — and current HEAD fails its own CI (mypy + coverage).**

| Gate | Status |
|---|---|
| Import / boot | ✅ (env required at import for 11 modules — F7-M-03) |
| Tests green | ✅ 1123/1123 |
| Coverage ≥80% aggregate | 🔴 **FAIL — 76.38%** |
| Coverage ≥80% per module | 🔴 12+ modules below (incl. 0%, 11%, 30%) |
| Ruff / format / isort / flake8 | ✅ ✅ ✅ ✅ |
| Mypy `--strict` | 🔴 **FAIL (collision, aborted)** |
| Bandit / deps-sync | ✅ ✅ |
| pip-audit | 🟡 installed; unverifiable in the offline review sandbox |
| **Order-path OPS ≤ self-limit 3** | ✅ **PASS (empirical ×2: 3/10 acquires)** |
| Kill switch wired + audited | ✅ |
| Idempotency keys | ✅ client-side (broker honoring unconfirmed — carried) |
| Circuit breakers all paths | ✅ |
| Holiday calendar / IST | ✅ |
| VIX risk-off control | 🔴 inert + BUY-blocking (F7-H-02) |
| Trailing stops operational | 🔴 never driven (F7-H-04) |
| Strategy engine per CMP (runtime) | 🔴 **dead — 1 source vs ≥3, and 3-fix vs diversity-4** (F7-C-02) |
| TradeDecision → Analyzer routing | 🔴 simulated, default-on (F7-H-01) |
| Docker runtime / non-root / metrics | ✅ |

**Minimum hard requirements before any live deployment:** F7-C-01 → F7-C-02 → F7-H-02 → F7-H-01 → F7-H-04 → F7-H-03 → F7-M-01/02 (CMP-correct thresholds + persistent counters) → F7-M-05. (Maps to TODO-1…17 in §0.)

---

## Appendix A — CMP (LOATS-CMP-13July2026) Conformance Matrix

### A.1 Zero-Assumption Rules (CMP §3 — NON-NEGOTIABLE)

| # | Rule | Evidence (both passes) | Verdict |
|---|---|---|---|
| 1 | NIFTY lot size 25 | `settings.py:77` nifty_lot_size=25 | ✅ |
| 2 | No 500ms resting time | No resting logic | ✅ (N/A) |
| 3 | Algo ID tagging broker's job; strategy field audit-only | No tag synthesis | ✅ |
| 4 | OPS threshold 10; self-limit ≤3 | **Empirical ×2: singleton True, max_ops=3=settings, 3/10 acquires**; factories default from settings (`rate_limiter.py:35-36`); call sites bare (`openalgo.py:820,897`) | ✅ **CONFORMANT (F6-C-01 closed)** |
| 5 | Paper = Analyzer Mode | `openalgo_mode="ANALYZE"` default | ✅ |
| 6 | Bot-logic trailing SL + SL-M | SL-M ✅; engine exists, **never driven** (F7-H-04) | 🟠 Partial |
| 7 | Modification limit 25/order | Gate hard-codes 25 ✅; **settings=30 mislabeled "CMP Rule 7: ≤30"**; counters fail-open, volatile | 🟠 Partial + misconfig |
| 8 | `as_of_date`; never `date.today()` | 0 × `date.today(` ✅; `as_of_date` convention absent | 🟡 Half |
| 9 | py_vollib; newspaper4k; VADER ±0.05 | vollib (documented successor) + newspaper4k + 0.05 | 🟡 Documented deviation |
| 10 | India VIX external input only | Setter exists, **zero callers**; gate runs on 18.5 fallback | 🔴 **Violated in effect (F7-H-02)** |
| 11 | Position limits 5 NIFTY / 3 BANKNIFTY | `max_nifty_positions=5`, `max_banknifty_positions=3` (`settings.py:102-106`) + `check_position_limits` in decision path | ✅ Fixed |
| 12 | Trailing = monotonic ratchet; SL-M | Ratchet math exists (11% cov); **no runtime driver** | 🟠 Partial |

### A.2 Phases (CMP §5)

| Phase | CMP gate | Verdict |
|---|---|---|
| P0 Scaffolding (3d) | gates clean | 🟠 Was green at FR5-era; **red at HEAD (F7-C-01)** |
| P1 Data layer (1wk) | live ANALYZE round trip | 🟠 Client ✅; round-trip latency unevidenced |
| P2 TA/VA + Strength (1.5wk) | 9/21/50/200, BBANDS 20, CCI 20, Hurst+ADX regime, composite strength | ✅ **Implemented** (`ta.py:385,414,447,546` + strength pkg) — composite starved at runtime (A.3) |
| P3 Sentiment Lite (1wk) | scores ∈ [-1,+1] | ✅ |
| P4 Strategy + Risk (2wk) | rules, strike, 2% sizing, trailing ratchet, VaR, kill switch, backtest sanity | 🟠 ~70% — all modules exist; BUY IV threshold wrong (F7-M-01); trailing undriven; `backtest_sanity` 0% + no caller; VaR ✅ |
| P5 Orchestrator + Analyzer (1wk) | 3 gates, per-source breakers, session lifecycle, ALL decisions → Analyzer, 2-wk forward test | 🟠 ~50% — thresholds ✅; session ✅; **source gate unsatisfiable at 3 sources AND starved at 1 (F7-C-02)**; routing simulated default-on (F7-H-01); per-source breakers ❌ (global only); forward test not begun |

### A.3 SEBI card & verification (CMP §6/§7)

Audit 7-yr ✅ (2555 d); SHA-256 append-only ✅; JSONL-first ✅ prod / ❌ test-bypass (F7-M-05). Verification gates: superset configured — **mypy + coverage RED at HEAD; pip-audit unverifiable offline**. Latency gates instrumented / live-validated ❌.

### A.4 Structure & hygiene (CMP §4/§8)

Flat package + empty CMP-named shells; stray `src/` layer breaks mypy. Secrets ✅. Compact-repo spirit 🟡 (root nominally clean but 47 root tracked files incl. junk; 343 tracked incl. 117 docs/reports).

**Conformance bottom line: closer, but still NO — not strict.** Rule 4 finally conforms (empirical, twice). Rule 10 violated in effect; Rule 7 carries a mislabeled 30; Rule 12's engine is dormant; P5's source-gate/routing requirements are violated in effect — and the implemented source gate **exceeds the plan's own 3-source wording**, so no compliant 3-source deployment is even possible without a threshold change. The strategy core now *exists in code* — this review chain's contribution is showing it does not yet *execute*.

---

## Appendix B — Finding Dispositions

### B.1 FR6 (15Aug2026) Finding Disposition (verified live by Investigator, re-verified by Reviewer)

| FR6 finding | Status at `163cdf9` | Evidence delta |
|---|---|---|
| F6-C-01 OPS cap 50 vs ≤3 | ✅ **CLOSED** | Probe: identity True; max_ops 3; 3/10 and 3/10 acquires; factories default from settings (`rate_limiter.py:36,149,180`); class ctors unchanged-correct |
| F6-C-02 gates red (ruff 135/format 20/isort 11) | 🟠 **HALF-CLOSED → F7-C-01** | ruff/format/isort/flake8 now ✅ clean; but mypy now 🔴 (new collision) and coverage 🔴 76.38% — different gates, same class of failure; misleading commits continue (4th review) |
| F6-H-03 aiosqlite tier 31% / teardown | 🟡 Mostly closed | Additions 71% (was 31%); teardown warnings gone (1 benign warning); pool lifecycle fixed; still <80% |
| F6-H-04 CMP strategy core absent | 🟠 **Half-real → F7-C-02/H-01/H-04** | Modules exist + wired; **runtime-dead (source gate)**; routing simulated; trailing undriven; backtest_sanity orphaned |
| F6-H-05 orchestrator defects ×7 | ✅ **CLOSED (7/7)** | Lazy settings `:162-165`; strong task ref `:122-123`; single increment `:807`; real drain `:836-847`; alert backoff 1/min `:140-144`; margin==0 guard `:577-586`; TA inside 80 ms window `:167-184` (Reviewer re-verified line-level 7/7) |
| F6-M-01 audit PYTEST bypass | 🔴 **NOT FIXED (claim false)** | `database.py:774` bypass present; commit `a03047e` claims it killed |
| F6-M-02 flaky `test_get_wait_time` | ✅ Closed | Not reproduced; 1123/0; clock-injection landed per commits |
| F6-M-03 advisory per-module gate | 🟡 Improved | Multiple `sys.exit(1)` paths added; final `exit(0)` at `:113` needs verification (F7-L-04) |
| F6-M-04 strike cache unbounded | ✅ Closed | TTLCache bounded |
| F6-M-05 weakened lint configs | 🟡 Partial | Ignore list deduped but still 20 rules incl. F401/I001 (F7-L-01); local mypy broken differently (collision) |
| F6-M-06 repo hygiene (38 root .py + 38 .md) | 🟡 Mixed | Root nominally cleaned ✅; but repo grew 302→343; strays moved to `src/`, `docs/audit-history/` (75 files), `reports/` (42) (F7-M-06/M-08) |
| F6-M-07 dev extras in Docker image | ✅ Closed | Multi-stage; `pip install --no-deps .`; non-root |
| F6-L-01 ambiguous unicode | ✅ Closed | ruff clean incl. RUF001-003 (no longer ignored) |
| F6-L-02 redis ghost import | ✅ Closed | Custom threading.Lock cache; no redis reference |
| F6-L-03 empty-match pytest.raises | ✅ Closed | No PytestWarnings in run |
| F6-L-04 AsyncMock misuse | ✅ Closed | No RuntimeWarnings in run |
| F6-L-05 duplicate healthchecks | ✅ Closed (not re-observed) | — |
| F6-L-06 bloombergquint feed | 🟡 Carried | Feed list still unvalidated |
| F6-L-07 `ta` dep unused | 🟡 Carried | Still declared, unused |

### B.2 Investigator (FR7) ↔ Reviewer (FR7-R) Disposition — all findings independently re-verified live

| FR7 finding | Reviewer verdict | Evidence delta |
|---|---|---|
| F7-C-01 mypy exit 2 + coverage gate fail | ✅ **Confirmed** | Mypy error reproduced verbatim; coverage 76.38% (vs 76.36% — jitter); **pip-audit sub-claim corrected: installed 2.10.1, Investigator's `-m pip-audit` invocation invalid; network-blocked here, not absent** |
| F7-C-02 source gate dead (1 unique vs ≥3) | ✅ **Confirmed + EXTENDED** | Empirical: production-shaped 3× source="orchestrator" → rejected (available 1/required 3). **NEW: second stacked diversity gate (≥0.5 of 7 enum sources) mathematically requires 4 distinct producers — 3-tagged-source fix insufficient (0.4286 < 0.5); 4 sources pass (0.5714). Unknown source strings silently map to TECHNICAL_ANALYSIS.** |
| F7-H-01 routing stub | ✅ Confirmed + aggravated | Docstring/sleep/fabricated-success re-read; **`analyzer_routing_enabled=True` default — fabrication is default-on**; stub body `:238-274` itself untested |
| F7-H-02 VIX unwired, 18.5 bias | ✅ Confirmed | `set_vix_level` grep: definition only; BUY `vix<15` unreachable at 18.5; SELL `vix>15` vacuous |
| F7-H-03 untested new modules | ✅ Confirmed | Live coverage table: trailing 11%, backtest 0%, trade_decision 30%, orchestrator 67% w/ `:638-737` missing, options 66% |
| F7-H-04 trailing never driven | ✅ Confirmed | `update_trailing_stop` zero call sites; only `initialize` at `trade_decision.py:145` |
| F7-M-01 BUY IV-rank 60 vs 30 | ✅ Confirmed | `rules.py:256-257` |
| F7-M-02 mod-limit 30 vs 25, fail-open | ✅ Confirmed | `settings.py:99-101` + `openalgo.py:514` + `rules.py:419-420` |
| F7-M-03 eager settings ×10 | ✅ Confirmed, **11 not 10** | + `trailing_stop.py:28` |
| F7-M-04 dual signal engines | ✅ Confirmed | Legacy `:187` every cycle; thresholds 0.6 vs 0.5 (`trade_decision.py:88`) |
| F7-M-05 audit test-bypass persists | ✅ Confirmed | `database.py:774` |
| F7-M-06 src/ strays + shells | ✅ Confirmed | 8 strays + 7 shells (159-175 B) by listing |
| F7-M-07 options 90→66% | ✅ Confirmed | Coverage table |
| F7-M-08 repo 343 files | ✅ Confirmed, one count corrected | `docs/audit-history/` = **75** (not 76); `reports/` = 42; root junk `$null`, `[100%]`, `0.21.0` tracked |
| F6-C-01 closure (OPS ≤3) | ✅ **Re-confirmed empirically** | Identity True; max_ops 3; settings 3; **3/10 + 3/10** acquires |
| F6-H-05 closure (7/7 orchestrator fixes) | ✅ **Re-confirmed line-level** | `:122-123` task ref+callback, `:140-144` backoff, `:162-165` lazy settings, `:167-184` TA-in-window+cancel, `:577-586` margin==0 guard, `:807` single increment, `:836-847` real drain |
| F7-L-01…07 | ✅ Confirmed (L-02 corrected as above) | — |

**Zero refutations. Zero material contradictions — one material EXTENSION (C-02 diversity gate), two corrections (pip-audit installed; eager-settings count 11), two quantification updates (docs count 75; coverage 76.38%).** The Investigator's FR7 report stands as accurate; this consolidated report is the authoritative final deliverable of the 23Aug2026 review chain.

---

## Appendix C — Verification commands (re-runnable, evidence basis of both passes)

```powershell
$py = '.\LOATS13July2026\Scripts\python.exe'

# State
git rev-parse HEAD            # 163cdf9a674a6e9c4d373d2d2481f3f47cd52cf3
git status --short            # clean (untracked review artifacts only)

# Gates (clean venv; flake8 reads .flake8)
& $py scripts\check_deps_sync.py                                  # PASS
& $py -m ruff check src/ tests/ scripts/ --config pyproject.toml  # PASS (0)
& $py -m ruff format --check src/ tests/ scripts/                 # PASS (132 files)
& $py -m isort --check-only src/ tests/ scripts/ --settings-path pyproject.toml  # PASS
& $py -m flake8 src/ tests/ scripts/                              # PASS
& $py -m mypy src/ --strict --config-file pyproject.toml          # FAIL exit 2 (collision)
& $py -m bandit -r src/ -c pyproject.toml -q                      # PASS
& $py -m pytest tests/ --cov=src --cov-branch --cov-fail-under=80 -q
#   → 1123 passed, 1 warning; coverage 76.38% (Reviewer) / 76.36% (Investigator) → GATE FAIL (exit 1)

# pip-audit (Reviewer correction: it IS installed)
& $py -m pip show pip_audit                                       # Version: 2.10.1
& .\LOATS13July2026\Scripts\pip-audit.exe                         # blocked by sandbox network egress

# F6-C-01 closure reproduction (OPS self-limit) — run in both passes
$env:OPENALGO_API_KEY='probe'
# → singleton identity: True; effective max_ops: 3; settings.max_ops: 3
# → order acquires passed: 3/10; smart acquires passed: 3/10

# F7-C-02 reproduction (dead CMP chain + Reviewer diversity extension)
git grep -n '"source": "orchestrator"' -- src/loats/orchestrator.py   # :271 :338 :480
# strength/__init__.py:384  len(source_set) < 3         → production supplies 1  → REJECT
# strength/__init__.py:396  diversity_score < 0.5 (=3.5 of 7 enum)     → 3 sources = 0.4286 → REJECT
#                                                                   4 sources = 0.5714 → PASS
# Live probes (Reviewer pass, verbatim outcomes):
#   3× source="orchestrator"          → (False, insufficient_unique_sources, available=1)
#   ta+sentiment+price_action         → (False, insufficient_source_diversity, 0.4286)
#   ta+sentiment+price_action+volat.  → (True,  source_validation_passed,  0.5714)
```

## Appendix D — "Not enough evidence" disclosures

- **pip-audit gate state at HEAD:** tool installed (2.10.1); two execution attempts in the review sandbox timed out fetching the vulnerability database (no network egress). Verdict: unverifiable here — re-run in a network-enabled environment. (Investigator's "not installed" was an invocation error — corrected, Appendix B.2.)
- **OpenAlgo server-side honoring of `Idempotency-Key`:** not verifiable from the repository (documented as unconfirmed, `openalgo.py:23-31`) — carried.
- **Live ANALYZE-mode round-trip latency (P1 gate) and the P5 2-week forward test:** no run-log evidence on disk — carried.
- **`security.yml` weekly workflow results:** workflow present; executions not inspected.
- **`check_per_module_coverage.py` final exit semantics:** not fully traced (F7-L-04).
- **Behavior of the CMP chain under real multi-source feeds:** cannot be observed — production produces one source; the Reviewer pass additionally shows that even 3 correctly-tagged sources cannot pass the diversity gate (that IS the F7-C-02 extension).
- **Coverage drift:** Investigator 76.36% vs Reviewer 76.38% on the same HEAD — timing jitter in branch coverage; both FAIL the 80% gate.

---

**End of Consolidated Review #7 (FR7 Investigator + FR7-R Reviewer). REVIEW-ONLY deliverable — no code modified. All recommendations (§0 TODO-1…27) require explicit USER APPROVAL before implementation.**

**Summary:** The FR7 Investigator's audit is accurate — every finding re-confirmed live by the Reviewer, zero refutations. The review chain adds three things: (1) the source gate is **doubly dead** — production supplies 1 unique source against the ≥3 rule, AND the stacked diversity gate (≥0.5 of 7 enum sources) mathematically requires **4** distinct producers, so the obvious 3-producer fix is insufficient and the implemented gate is stricter than the CMP's own "≥3 sources" wording; (2) pip-audit **is installed** (2.10.1) — the Investigator's hyphenated invocation was the error; the gate remains unverifiable only because the review sandbox blocks the vulnerability-DB network fetch; (3) eager settings afflict 11 modules, not 10. Meanwhile the wave's real wins are re-confirmed: OPS ≤3 empirically enforced twice, all seven orchestrator defects fixed, CMP strategy modules present. HEAD still fails mypy (exit 2) and coverage (76.38% < 80) while commit messages claim full compliance — the fourth consecutive review to document that pattern. **NOT READY for live capital. ANALYZE-mode demo only.**

*Note: this report file is itself an untracked repo-root artifact — relocate to `docs/audit-history/` or remove before any release, per F7-M-08. (The two source FR files have already been archived there.)*
