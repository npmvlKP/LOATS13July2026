# LOATS13July2026 — FR9 Forensic Engineering Review Report (15Sep2026 · FINAL, sedrm protocol)

**Date:** 2026-09-15 · **Project:** LOATS13July2026 — Lite OpenAlgo Trading System (Indian equities/options research; OpenAlgo REST in ANALYZE mode; Telegram alerts; orchestrator analysis pipeline)
**Source Folder:** `G:\.OA\LOATS-13July2026\LOATS13July2026` · **Python:** 3.12.7 · **Venv:** `loatsNEW` · **Git:** https://github.com/npmvlKP/LOATS13July2026.git
**Reviewed at:** HEAD `57b77a0`, branch `main`, origin in sync, working tree clean, 419 tracked files, post-`git filter-repo` history (FR8 SHA `28ab454` no longer resolvable — purge executed per FR8 roadmap).
**Master plan audited against:** `LOATS-CMP-13July2026.txt` (LITE edition; re-attached 15Sep, byte-identical to the governing plan).
**Governing question:** Was the project built strictly as per the CMP; what remains to be implemented/refactored, in priority sequence?
**Status:** ✅ **USER APPROVAL RECORDED 15Sep2026** — Wave 1 + TODO-7 approved for execution under the STRICT LOATSEV protocol (BUILD → IMPLEMENT → INTEGRATE → REFACTOR → OPTIMIZE → VERIFY → IDENTIFY → ROOT-CAUSE → FIX → TEST → RECHECK → FIX → RE-VERIFY → CONFIRMED & VERIFIED SUCCESS → COMPREHENSIVE SUMMARY). Waves 2–4 gated on Wave-1 re-verification.
**Mode:** REVIEW ONLY until per-item approval; this file supersedes every earlier TODO list for this project.

**Reviewers (Senior Engineering Review Board):** Principal Software Architect · Senior Python Engineer · Senior Code Reviewer · Production Debugging Engineer · Performance Optimization Engineer · Scalability Engineer · Security Auditor · DevOps & Infrastructure Engineer · QA / Test Architect · Reliability Engineer (SRE) · Technical Lead · Systems Design Reviewer.

**Evidence basis (all re-executed live this session, clean venv, HEAD `57b77a0`):** deps-sync PASS; ruff check+format PASS; isort/flake8 PASS; `mypy src/ --strict` PASS (38 files); bandit PASS; pip-audit 0 vulns; gitleaks no leaks; **pytest --cov-fail-under=80 → 1841 passed / 1 skipped / 0 failed, 88.93%, 486 s** (full live run — corrects the stale 07Sep archive figure 1523/87.49%); per-module floors ALL PASS (full 10-module FR map); `fr7_health_check.py` full → 31 PASS / 0 FAIL (one transient HC-12 = coverage-lock mutex working as designed); CI green on `origin/main` (PRs #24–#42); empirical probes: OPS limiter 3/10 acquires, Rule-7 reserve/release (26th raises, restart-surviving, per-order isolated), diversity gate (3 src → 0.4286 reject; 5 src → 0.714 pass; +unknown → excluded-and-audited), IV-rank saturation (synthetic + 527/527 live rejects at exactly 100.0), bare-env import OK; live-store forensics: 10,013 audit rows, 102,525 signals, 1,542 decisions (all BUY/PENDING, `as_of_date` NULL), 15 ROUTE rows in the P5 window all `routing_enabled:false`; `:8001` metrics (816 cycles, avg 7.49 s, max 122.6 s, target_compliance_count=0); `gh api branch-protection/main` → 404 with admin token; process table (P5 supervisor PIDs 22072/22088).

---

## 1. Critical Findings

### 🔴 F9-C-01 — `calculate_iv_rank` is dimensionally wrong: IV-rank saturates to 100.0; CMP BUY gate unreachable on real data (TODO-1)

- **Issue ID:** F9-C-01 (→ TODO-1) · **Category:** CMP Conformance / Correctness (financial decisioning) · **Severity:** Critical · **Confidence Level:** Certain (source read + synthetic probes + live DB)
- **Evidence:** (1) `src/loats/rules.py:143-172` — `std_dev = np.std(returns) * np.sqrt(252)` (ANNUALIZED) is divided by the spread of DAILY `min/max(returns)` → raw ratio ≈ 4–6 → `np.clip(…*100, 0, 100)` → **100.0 always**. (2) Synthetic probe: daily-vol regimes 0.5 %/1 %/2 % → iv_rank = 100.0 in all three. (3) Live DB: **527/527** gating rejects since 08Sep carry `iv_rank: 100.0` (100 % saturation). (4) CMP §4 rules mandate BUY at `IV rank < 30` — mathematically unreachable with sufficient data. (5) The 1,542 BUY/PENDING decisions all formed via the silent `len < window → return 0.5` insufficient-data fallback (see F9-M-04) — decisions are fallback artifacts, not strategy output. (6) Conceptual: the function computes an HV percentile and names it IV Rank; CMP means the rank of the instrument's IMPLIED volatility in its own historical IV range.
- **Root Cause:** Unit mismatch (annualized vs daily) masked by a clip; no property/bounds test ever asserted a non-degenerate distribution.
- **Technical Explanation:** With `σ_ann ≈ 0.14` vs daily return range `≈ 0.03`, the ratio is always ≫ 1; the clip guarantees saturation. Every gating evaluation therefore sees a fake "IV extremely high" market.
- **Impact:** The core CMP rules gate is decorative; strategy can only ever evaluate SELL; false market-state signal fed to every gating decision since go-live.
- **Possible Consequences:** Systematic mis-signalling; BUY branch dead in production; any future LIVE authorization resting on never-validated strategy logic.
- **Risk Assessment:** Critical — core function; likelihood certain (deterministic arithmetic).
- **Suggested Resolution:** (a) Compute true IV rank from option-chain IV the orchestrator already fetches (BS IV via `options_math.py`): `rank = (current_ATM_IV − min(series)) / (max(series) − min(series)) × 100` over a 252-day persisted IV series keyed symbol+as_of_date. (b) If an HV fallback must remain: consistent units (percentile of daily σ within the window), renamed `hv_rank`. (c) Kill the silent 0.5 fallback (merges F9-M-04): insufficient history ⇒ loud `insufficient_history` blocking BOTH directions + audit row.
- **Recommended Tests:** (1) property test — randomized fixtures yield values across [0,100], not constant (old code must FAIL); (2) replay over stored `historical_data` → <90 % of cycles at any single value; (3) BUY reachable at fixture 25, SELL at 45, boundaries 30/40; (4) IV-series rank vs hand-computed; (5) insufficient-history blocks both directions + audits.
- **Estimated Complexity:** 0.5–1 day · **Dependencies:** none · **Priority: P0 — execute FIRST.**

### 🔴 F9-C-02 — P5 forward-test evidence INVALID: supervisor enables routing but the deciding engine routes `disabled`; counters 0/0/0 vs 15 DB ROUTE rows (TODO-2)

- **Issue ID:** F9-C-02 (→ TODO-2) · **Category:** CMP P5 conformance / Observability integrity · **Severity:** Critical · **Confidence Level:** Certain for the divergence; root-cause mechanism **Not enough evidence** (candidates enumerated below)
- **Evidence:** (1) Run log `reports/p5_forward_test_20260912_150243.json`: events `routing_enabled` at 01:52:55Z and 04:14:19Z on 15Sep; `counters: {success:0, disabled:0, error:0}`; cycles 570. (2) DB ROUTE rows in the same window: **15, every one `routing_enabled:false`, outcome `analyzer_routing_disabled`** — including `decision_20260915020458…` at 02:04:58Z, **12 minutes AFTER** the enable event. (3) `logs/loats.log`: `Enabled Analyzer routing` 01:52:55.934 → `Analyzer routing disabled for decision …02:04:58` 02:04:58.002; no intervening disable line. (4) 02:05:51Z shows Enabled→Disabled 7 ms apart (PR-#42 dry-run smoke lifecycle — timing consistent, attribution unproven). (5) Counter non-reconciliation: run-log 570 cycles vs `:8001` 816 cycles and ~4,600 signals/day/source in DB. (6) `verify_p5_forward_test.py` honestly grades the run INCOMPLETE ("no decisional activity recorded… cycles alone do not satisfy P5").
- **Root Cause:** The engine instance that decides/routes reads `analyzer_routing_enabled=False` during windows in which the supervisor asserts it enabled the singleton. Candidates (unresolved): second engine process alive at decision time (not in current Win32_Process listing); lazy-singleton rebuild during `TradingSystem.initialize()`; supervisor sampling a different instance than the router.
- **Technical Explanation:** P5 evidence is accrued by a supervisor whose measured counters never move, while the DB accumulates routing outcomes that contradict the supervisor's claimed state — the evidence stream cannot support the P5 gate regardless of which mechanism applies.
- **Impact:** The 14-day P5 span (day 8/14) is void; if cited it would be the chain's 6th false-readiness record.
- **Possible Consequences:** A 21Sep artifact that fails grading — or worse, gets cited as evidence; LIVE authorization on unverified routing.
- **Risk Assessment:** Critical for P5; certainty of divergence established.
- **Suggested Resolution:** (1) Stop supervisor (PIDs 22072/22088); archive run logs to `docs/audit-history/` marked INVALID-EVIDENCE. (2) Instrument `id(trade_decision_engine._instance)` + flag state at enable/cycle-start/route-time. (3) Process-wide engine registry/single-construction guard. (4) Self-verifying evidence: ROUTE row with `routing_enabled:false` during a claimed enabled window ⇒ CRITICAL alert + auto-FAIL the run. (5) Reconcile counters from DB ROUTE rows (source of record). (6) After F9-C-01/F9-H-04 land: restart the 14-day span with `--ack-live-endpoint`; verify first ROUTE row `routing_enabled:true` within one decision cycle; include a Telegram kill-switch verification event (CMP P5 gate).
- **Recommended Tests:** (1) enable → forced decision → ROUTE row `true` + counter delta ≥1 (RED today); (2) flag-reset mid-run ⇒ verifier grades INVALID; (3) counters == DB rows at every sample; (4) `/kill` Telegram test-double blocks next order and is logged.
- **Estimated Complexity:** 0.5–1 day + 14-day re-run · **Dependencies:** F9-C-01, F9-H-04 · **Priority: P0.**

---

## 2. High Priority Findings

### 🟠 F9-H-01 — CMP decision-gate thresholds swapped & loosened: 0.5/0.6 vs CMP 0.6/0.4 (TODO-13)

- **Issue ID:** F9-H-01 (→ TODO-13) · **Category:** CMP Conformance (§4 orchestrator gates) · **Severity:** High · **Confidence:** Certain
- **Evidence:** CMP §4: `|score|>0.6, no opposition>0.4`. Build: `composite_strength_threshold=0.5` (`config/settings.py:57-59`); `opposition_threshold=0.6` as a hardcoded attr (`strength.py:126`, block condition `:281 strength > 0.6`). Both gates looser than CMP; no ADR defends the swap — values appear accidental.
- **Root Cause:** Transcription drift at implementation; opposition threshold never lifted into Settings.
- **Technical Explanation:** Composite 0.55 passes today (CMP: reject); opposing signal 0.45 does not block today (CMP: block). Strictly more decisions flow than the CMP design permits.
- **Impact / Consequences:** Gate calibration off-spec; conflates review of every downstream decision made to date.
- **Risk Assessment:** High (conformance), certain.
- **Suggested Resolution:** Set `composite_strength_threshold=0.6`; move `opposition_threshold` into Settings at `0.4`; update pinned tests with CMP-citation comments; conformance test asserting both values. If different values are ever wanted: ADR first.
- **Recommended Tests:** 0.55 → rejected / 0.65 → proceeds; opposition 0.45 → blocked / 0.35 → not; settings conformance asserts 0.6/0.4.
- **Estimated Complexity:** 1–2 h · **Dependencies:** none (land with F9-C-01) · **Priority: P1.**

### 🟠 F9-H-02 — CMP latency gate "orchestrator cycle <100 ms" abandoned de facto: 8.0 s window, 0/816 cycles compliant (TODO-3)

- **Issue ID:** F9-H-02 (→ TODO-3) · **Category:** CMP Conformance (§1/§7 latency gates) · **Severity:** High · **Confidence:** Certain
- **Evidence:** `settings.producer_window_seconds=8.0` (`settings.py:94-106`, rationale comment; ADR-006 §375-383 documents the move off 80 ms); live `:8001/metrics` → `{count:816, average:7.49 s, max:122.6 s, target_compliance_count:0}`. No CI gate, no health check on cycle latency; strike <5 ms / trail <1 ms benchmarked but unenforced.
- **Root Cause:** The 80 ms window starved producers under real feed latency (documented); the correction overshot to 8 s without amending the CMP gate.
- **Technical Explanation:** Inline RSS/history fetches in the producer path make sub-100 ms physically unachievable; the CMP budget was silently dropped rather than re-architected or amended.
- **Impact / Consequences:** Conformance reports cite latency gates production has never met; LIVE authorization would rest on unvalidated latency characteristics.
- **Risk Assessment:** High.
- **Suggested Resolution:** USER DECISION required: (a) restore sub-100 ms hot loop by decoupling producers (background tasks + last-known-good snapshots; hot loop reads cache), or (b) ADR-amend with a measured budget (e.g. cycle P99 ≤ 250 ms hot; producers ≤ 8 s async; strike <5 ms; trail <1 ms). Either way: wire `benchmark_performance.py` into CI as a gate; add cycle-compliance ratio to the health check.
- **Recommended Tests:** CI benchmark gate (strike P99 ≤ 5 ms, trail P99 ≤ 1 ms); health-check compliance floor; 1 Hz load test with fixture feeds.
- **Estimated Complexity:** 1–3 days (a) / 2 h (b) · **Dependencies:** none · **Priority: P1 (decision first).**

### 🟠 F9-H-03 — Sentiment producer effectively DEAD: last signal 13Sep 01:59 UTC; 8–10 s analysis vs 8.0 s window (TODO-4)

- **Issue ID:** F9-H-03 (→ TODO-4) · **Category:** Reliability / CMP P3 · **Severity:** High · **Confidence:** Certain
- **Evidence:** DB per-day sentiment signals: 09Sep 29 · 10Sep 0 · 11Sep 0 · 12Sep 128 · 13Sep 65 · 14Sep 0 · 15Sep 0; every cycle logs `Sentiment analysis exceeded budget: ~8,000–9,900 ms`; feeds validate fine (3/3 live-validation PASS at 04:14Z); producer persists only when |score| ≥ 0.05 AND completes inside the window.
- **Root Cause:** Per-article network extraction (newspaper4k) inline in the producer; window < worst-case analysis; cancellation lands before `async_create_signal`. Diversity gate stays green on the other 4 sources — failure invisible to the chain.
- **Technical Explanation:** A 5-source design silently runs as 4; sentiment weight in `SOURCE_WEIGHTS` is dead weight; P3's mandate (news 70/social 30) doubly unmet (see F9-H-05).
- **Impact / Consequences:** Degraded signal basis; schedule-correlated blind spot no test observes (tests mock the boundary).
- **Risk Assessment:** High.
- **Suggested Resolution:** Cache article content per URL (TTL 5 min); extraction to a background task; cycle producer consumes last-known-good (tags `degraded` when stale); per-source liveness metric — alert if any source's latest signal age > 15 min during REGULAR session.
- **Recommended Tests:** warm producer persists < 1 s; liveness check fails on stale source; cold-cache serves last-known-good with `degraded` audit tag.
- **Estimated Complexity:** 0.5–1 day · **Dependencies:** none · **Priority: P1.**

### 🟠 F9-H-04 — `as_of_date` plumbed but NEVER supplied: 0/1,542 decisions, 100 % of ROUTE rows NULL (CMP Rule 8) (TODO-5)

- **Issue ID:** F9-H-04 (→ TODO-5) · **Category:** CMP Rule 8 · **Severity:** High · **Confidence:** Certain
- **Evidence:** Column + param + ROUTE audit field exist; orchestrator call site (`orchestrator.py:1552-1561`) passes nothing; DB: 0 non-null of 1,542; every ROUTE row `as_of_date:null`. Positive: zero `date.today(` in src (re-verified).
- **Root Cause:** The parameter was built (F8-L-02 half-close) but the production caller was never wired.
- **Technical Explanation:** CMP Rule 8 requires explicit snapshot dating so decisions are reproducible against the data they were computed from; NULL defeats the traceability the column exists for.
- **Impact / Consequences:** Decisions not attributable to a data snapshot; audit trail loses its reproducibility anchor.
- **Risk Assessment:** High (compliance), certain.
- **Suggested Resolution:** Derive snapshot date from input history/quote payload timestamps (not wall clock) at the decision call site; persist on decision + ROUTE row; legacy rows stay NULL (honest backfill rule).
- **Recommended Tests:** decision `as_of_date` == max timestamp of input batch; ROUTE row matches; T-1 data records T-1.
- **Estimated Complexity:** 2–4 h · **Dependencies:** none · **Priority: P1.**

### 🟠 F9-H-05 — P3 sentiment spec undelivered: no 70/30 ensemble, no 4 h half-life decay, bounds not enforced (TODO-14)

- **Issue ID:** F9-H-05 (→ TODO-14) · **Category:** CMP Conformance (P3) · **Severity:** High · **Confidence:** Certain
- **Evidence:** CMP P3: "RSS+VADER ensemble (news 70/social 30), decay. Gate: scores always [-1,+1]". Greps: no ensemble weighting, no decay function, `SentimentAnalysisResult.sentiment_score: float` unbounded (models.py:429); VADER-mean keeps range functionally only; no property test.
- **Root Cause:** P3 shipped as RSS+VADER-mean only; ensemble/decay/bounds never implemented and never re-flagged by the FR chain until this clause-by-clause pass.
- **Impact / Consequences:** Signal quality below spec; silent out-of-range risk if scoring ever changes.
- **Risk Assessment:** High (conformance).
- **Suggested Resolution:** (1) `sentiment_score: float = Field(ge=-1.0, le=1.0)`; (2) decay `0.5 ** (age_hours/4)` before averaging; (3) 70/30 weight scaffold — news 1.0 with explicit ADR note deferring the social leg (do NOT fabricate a social score).
- **Recommended Tests:** bounds fuzz property; decay monotonicity; ensemble arithmetic vs hand-computed; model rejects out-of-range.
- **Estimated Complexity:** 0.5 day · **Dependencies:** F9-H-03 (producer must persist again) · **Priority: P1.**

---

## 3. Medium Priority Findings

### 🟡 F9-M-01 — Audit trail is self-hashed, NOT chained: "SHA-256 chain" (CMP §2/§4/§6 kept-list) unimplemented (TODO-6)
- **Issue ID:** F9-M-01 (→ TODO-6) · **Category:** CMP conformance / audit integrity · **Severity:** Medium · **Confidence:** Certain
- **Evidence:** `database.py:762-770` hashes entry's own fields only; no `previous_hash` in schema, JSONL keys, or ANY git history (`git log -S previous_hash` → empty); `verify_audit_log_integrity()` re-computes self-hashes (True on live 10,013-row log). README:163 claims "SHA-256 chained".
- **Root Cause:** Chain semantics claimed at plan level; implementation delivered per-entry integrity only.
- **Technical Explanation / Consequences:** An attacker (or accident) deleting/reordering entries and recomputing self-hashes is undetectable — defeats NIST AU-9 tamper-evidence intent.
- **Risk Assessment:** Medium (integrity), certain.
- **Suggested Resolution:** Add `previous_hash` column; hash = `sha256(entry || prev_hash)`; both JSONL line and DB row carry it; verifier walks links; broken link ⇒ FAIL + CRITICAL alert; one-time migration seeds at current head.
- **Recommended Tests:** mutate/delete/reorder a middle entry ⇒ FAIL each way; 1k fresh chain PASSES; migration preserves pre-migration prefix.
- **Estimated Complexity:** 0.5 day · **Priority: P2.**

### 🟡 F9-M-02 — Branch protection on `main` STILL absent (3rd consecutive review); now one API call away (TODO-7)
- **Issue ID:** F9-M-02 (→ TODO-7) · **Category:** DevOps / SCM integrity · **Severity:** Medium · **Confidence:** Certain
- **Evidence:** `gh api repos/npmvlKP/LOATS13July2026/branch-protection/main` → **404** with authenticated admin token (`permissions.admin=true`) — no rule exists. Filter-repo purge done; PR-flow habit established (#24–#42).
- **Root Cause:** Perpetually deferred manual gate.
- **Risk Assessment:** Medium; history-rewrite protection absent on a public repo.
- **Suggested Resolution:** `gh api -X PUT …/branches/main/protection` — required CI contexts, ≥1 review, dismiss-stale, include-admins; save response JSON to `docs/audit-history/`.
- **Recommended Tests:** GET → 200 with contexts; direct push rejected (capture 403).
- **Estimated Complexity:** 15 min · **Priority: P2 — do TODAY regardless of wave.**

### 🟡 F9-M-03 — Analyzer decision-intake endpoint deferred: routing can only ever record honest 404s (TODO-8)
- **Issue ID:** F9-M-03 (→ TODO-8) · **Category:** CMP P5 completeness · **Severity:** Medium · **Confidence:** Certain
- **Evidence:** `analyzer_intake_path="analyze"` 404s by design (ADR-006 Am.5); no intake handler in-repo; OpenAlgo core may not be modified (adapter rule) so intake must live in OpenAlgo extension points or a documented gateway sidecar.
- **Risk Assessment:** Medium — P5 "route ALL" cannot fully close without a decision here.
- **Suggested Resolution:** USER DECISION: (a) audited-attempt semantics (ADR-amend P5 acceptance, 2 h) or (b) stand up the intake endpoint (1–2 days). Update `verify_p5_forward_test.py` to grade under the chosen semantic. **RESOLVED (a) 2026-09-18:** audited-attempt semantics — ADR-006 Amendment 7 (`routed_decisions` counter, `analyzer_intake_semantic` machine-readable single source, grader attempt-gate); PR #56.
- **Recommended Tests:** verifier PASS only under chosen semantic; routed decision reaches intake (b) or is audited 404 (a). Pinned: `tests/test_f9m03_audited_attempt.py` (per-path attempt counting, grader attempt-gate branches) and the Am.7 semantic-source pin in `tests/test_analyzer_intake_contract.py`; legacy logs grade unchanged.
- **Estimated Complexity:** 2 h / 1–2 d · **Dependencies:** F9-C-02 · **Priority: P2.** · **Status: ✅ CLOSED 18Sep2026 (PR #56).**

### 🟡 F9-M-04 — Silent `0.5` fallback in `calculate_iv_rank` lets insufficient data pass the BUY gate (TODO-9; folds into F9-C-01)
- **Issue ID:** F9-M-04 (→ TODO-9) · **Category:** Edge-case correctness · **Severity:** Medium · **Confidence:** Certain
- **Evidence:** `rules.py:158-159` — `len(historical_data) < window → return 0.5`; 0.5 % < 30 ⇒ BUY leg passes on insufficient data; all 1,542 BUY/PENDING decisions trace to this path or the saturated gate.
- **Suggested Resolution / Tests:** insufficient history ⇒ loud `insufficient_history` blocking BOTH directions + audit row; boundary `len == window` computes for real. Verified during F9-C-01 RE-VERIFY. **Complexity:** 1 h inside F9-C-01 · **Priority: P2.**

### 🟡 F9-M-05 — Strike selection off-spec: no true 0.50–0.60 delta band; SELL-side 2SD absent (TODO-15)
- **Issue ID:** F9-M-05 (→ TODO-15) · **Category:** CMP Conformance (§4 strike) · **Severity:** Medium · **Confidence:** Certain
- **Evidence:** CMP: "delta 0.50-0.60 buy; 2SD sell; OI check". Build: `atm_straddle`/`delta_neutral`/`oi_based` strategies; delta logic is a "prefer close to 0.5" heuristic (`strike_selection.py:208-212`); **zero 2σ logic anywhere** (grep empty); OI check ✅.
- **Suggested Resolution:** Buy-side filter |delta| ∈ [0.50, 0.60]; sell-side 2σ band from consistent-unit history σ (daily σ scaled by √days); OI as confirmation filter; boundary tests at 0.49/0.50/0.60/0.61, 2σ vs hand-computed, OI-missing fail-closed.
- **Estimated Complexity:** 0.5–1 day · **Priority: P2.**

---

## 4. Low Priority Findings

- **🟢 F9-L-01 (TODO-10) — Budget-warning noise:** ~13,000 meaningless warnings/log (4,172 TA + 5,032 sentiment + 4,165 volatility vs 30/40/30 ms budgets while the design window is 8 s). Fix: derive thresholds from `producer_window_seconds` (warn > 50 % of window) or restore CMP values if F9-H-02 revives sub-100 ms. Tests: no warning < 50 % window; warning above. 30 min. P3.
- **🟢 F9-L-02 (TODO-11) — Trailing driver default OFF** (`enable_trailing_stops=False`): CMP Rule 12 ratchet unexercised in the P5 run (no positions in ANALYZE — acceptable). Enable for supervised runs (same pattern as routing enable); ADR note. Tests: run-log records driver active; SL-M emission on open-position fixture. 1 h. P3.
- **🟢 F9-L-03 (TODO-12) — Live-store hygiene:** `STRESS-ORD` test row (02Sep) in `modification_counts`; 42 legacy NULL/`"orchestrator"`-source signals (14Aug, pre-tagging). Audited purge script + insert-time enum-source guard. Tests: script idempotent; guard rejects NULL/unknown. 1–2 h. P3.
- **🟢 F9-L-04 (TODO-16) — Kill-switch escalation absent:** CMP §4 names THROTTLE→PAUSE→KILL (MiFID II Art.17); build is binary activate/deactivate + OPS limiter as implicit throttle. ADR-accept short-term; build the 3-state machine if LIVE filing is anticipated. Tests (if built): threshold transitions; PAUSE blocks entries/allows exits; KILL blocks all + Telegram notify. 0.5 d or 30 min ADR. P3.
- **🟢 F9-L-05 (TODO-17) — CMP supersession register missing:** ADR-0003 (drop `ta`), 0004 (hand-rolled vol math), 0005 (scheduler cadence retired), flat-layout acceptance, threshold amendments (F9-H-01/H-02) — scattered; next review re-derives the delta by hand. One cross-referencing ADR. 30 min. P3.
- **🟢 F9-L-06 — Carried/watchlist:** P1 latency live round-trip re-measurement (post-F9-H-02); broker-side `Idempotency-Key` honoring (not verifiable in-repo); `security.yml` weekly run results uninspected.

---

## 5. Performance Review

| Item | Status | Evidence |
|---|---|---|
| Cycle < 100 ms | 🔴 **ABANDONED de facto** | 8.0 s producer window; 0/816 compliant; avg 7.49 s, max 122.6 s (`:8001`) → F9-H-02 |
| Strike < 5 ms | 🟡 benchmarked, not CI-enforced | `benchmark_performance.py` exists; no gate |
| Trail < 1 ms | 🟡 same | 93.2 % covered; default OFF (F9-L-02) |
| Producer window | ✅ semantically sound | both timeout AND exception paths cancel all producers; 50 ms settle grace (ADR-0007) |
| SQLite | ✅ | WAL; dual-write JSONL+row; `busy_timeout=30 s`; aiosqlite pool + to_thread |
| Caches | ✅ | thread-safe TTL; sub-µs hits; VIX TTL-cached |
| NumPy/numba | ✅ | vectorized indicators; numba Supertrend |
| Log noise | 🟡 | 10 MB/day rotation; ~13 k budget warnings (F9-L-01) |

No N² regressions; no new blocking I/O on the loop beyond the documented producer-window design.

## 6. Security Audit

| Check | Status | Evidence |
|---|---|---|
| Bandit / pip-audit / gitleaks | ✅ / ✅ 0 vulns / ✅ no leaks | re-run this session |
| Secrets | ✅ | `.env` untracked; SecretStr; no default key; no SecretStr logging |
| SQLi | ✅ | parameterized only |
| Telegram | ✅ | admin allow-list; `/kill` `/resume` gated; `html.escape` |
| TLS / kill switch / OPS ≤ 3 | ✅ | httpx verify; all order paths + loop + Telegram; live probe 3/10 |
| Idempotency | ✅ client-side | UUID/digest keys; broker-side honoring unconfirmed (carried) |
| SCM surface | 🟡 | branch protection absent (F9-M-02); public repo |
| Audit tamper-evidence | 🟡 | self-hash only, no chaining (F9-M-01) |

**Verdict:** application perimeter clean; residual security-adjacent exposure is SCM + audit-chain integrity, not code.

## 7. Scalability Review

Single-process by design (LITE). Event loop non-blocking ✅ (`to_thread` everywhere). Decision queue bounded with backpressure ✅. aiosqlite pool lifecycle clean. Cache thread-safe. Per-source breakers ✅. No new scaling limitations this wave; developer-scale operations restored post-purge (419 files).

## 8. Reliability Review

Kill switch ✅ (binary; escalation states → F9-L-04). Circuit breakers ✅ global + per-source. Retry/backoff/jitter ✅. NSE holiday calendar + IST ✅. Misfire handling ✅. Alert flood control ✅. Graceful shutdown ✅ (drain → scheduler → alerts → `async_close_all`). Audit dual-write atomic ✅ (JSONL-before-commit; suite-tested; no pytest bypass). **Open:** IV-rank saturation (F9-C-01), sentiment producer death (F9-H-03), P5 evidence divergence (F9-C-02), unchained audit (F9-M-01).

## 9. Maintainability Review

Good: LazyProxy generalizes lazy singletons with documented semantics; 15 ADRs; ADR-0007's empirical falsification of its own prior rationale is the chain's best engineering-note practice; single signal engine (ADR-0005); floor map with anti-narrowing guard; coverage-script exit semantics unit-tested. Eroding: thresholds that silently drifted from CMP (F9-H-01) show config-vs-plan drift has no conformance test; supersessions scattered (F9-L-05); commit messages again drifting toward essays in places.

## 10. Code Quality Review

| Gate | Result |
|---|---|
| deps-sync / ruff check / ruff format / isort / flake8 | ✅ PASS |
| mypy `src/ --strict` | ✅ 38 files, 0 issues |
| bandit / pip-audit / gitleaks | ✅ |
| pytest + coverage | ✅ **1841 / 1 skipped / 0 failed; 88.93 %** |
| Per-module floors | ✅ all 10 FR modules genuinely above floors |
| fr7_health_check (32 checks) | ✅ 31/0 (transient lock-contention explained) |

## 11. Testing Review

Strongest suite in the chain (1,170 → 1,841 tests since FR8; branch coverage on). Real gains: e2e now drives REAL producers (mocks only OpenAlgo/RSS boundaries — F8-C-01's fabrication cured, verified by reading the mock surface); Rule-7 +18 functional + multi-process stress; per-signal unknown-source exclusion; audit dual-write failure paths. **Gaps:** no property test caught the IV-rank constant (F9-C-01) — the exact class "deterministic outputs, property bounds" (P2 gate) was mandated to catch; no liveness test for producer persistence; no test exercises routing-enabled end-to-end (F9-C-02's RED test); strike band/2SD untested because unimplemented; latency gates unenforced in CI.

## 12. DevOps Review

CI (`ci.yml`): fail-fast chain incl. repo-hygiene (venv/env/junk rejection), RSS manifest validation, ruff×3, mypy strict, bandit, pip-audit, pytest + aggregate + per-module floors, docker build on PRs — all steps verified present; runs green on main. Security workflow present (weekly; results uninspected — carried). Docker: multi-stage, non-root, no dev extras. Metrics :8001 wired with cycle/chain counters. **Gaps:** branch protection (F9-M-02); benchmark gate absent (F9-H-02); this report is an untracked root artifact (relocate to `docs/audit-history/` before release).

## 13. Risk Matrix

| Finding | Severity | Likelihood | Impact | Risk |
|---|---|---|---|---|
| F9-C-01 IV-rank saturated; BUY unreachable | Critical | Certain | High (mandate no-op) | 🔴 |
| F9-C-02 P5 evidence invalid (flag divergence) | Critical | Certain | High (false-readiness risk) | 🔴 |
| F9-H-01 gate thresholds 0.5/0.6 vs CMP 0.6/0.4 | High | Certain | Medium | 🟠 |
| F9-H-02 latency gate abandoned (0/816) | High | Certain | Medium | 🟠 |
| F9-H-03 sentiment producer dead since 13Sep | High | Certain | Medium | 🟠 |
| F9-H-04 as_of_date never supplied | High | Certain | Medium | 🟠 |
| F9-H-05 P3 ensemble/decay/bounds absent | High | Certain | Medium | 🟠 |
| F9-M-01 audit unchained | Medium | Certain | Medium | 🟡 |
| F9-M-02 branch protection absent | Medium | Certain | Medium | 🟡 |
| F9-M-03 intake deferred | Medium | Certain | Medium | 🟡 |
| F9-M-04 silent 0.5 fallback | Medium | Certain | Medium | 🟡 |
| F9-M-05 strike band/2SD off-spec | Medium | Certain | Medium | 🟡 |
| F9-L-01…06 | Low | — | Low | 🟢 |

## 14. Technical Debt Assessment (ranked)

1. 🔴 F9-C-01 — strategy math correctness (everything downstream measures a broken gate).
2. 🔴 F9-C-02 — evidence-pipeline integrity (instrumentation, registry guard, DB-derived counters).
3. 🟠 F9-H-01/H-02 — CMP gate calibration (thresholds restore; latency budget decision + enforcement).
4. 🟠 F9-H-03/H-05 — sentiment subsystem (liveness + P3 spec completion).
5. 🟠 F9-H-04 — as_of_date end-to-end.
6. 🟡 F9-M-01/M-02/M-03/M-05 — audit chaining; branch protection; intake decision; strike spec.
7. 🟢 F9-L-01…06 — noise, trailing default, store hygiene, kill-switch states, supersession register, carried set.

## 15. Production Readiness Assessment

**Verdict: NOT READY for live capital. ANALYZE-mode demo only.** (9th consecutive review; first time every CMP §7 verification gate is simultaneously green AND the verifiers fail honestly — the remaining blockers are precisely enumerable below.)

| Gate | Status |
|---|---|
| All CMP §7 verification gates (ruff/format/mypy-strict/bandit/cov ≥ 80/pip-audit) + floors | ✅ live-green |
| OPS ≤ 3 · kill switch · idempotency · breakers global+per-source · holidays · Rule 7 persisted | ✅ live-probed |
| Rule 8 as_of_date | 🔴 FAIL (F9-H-04) |
| Rules gate math (IV rank) | 🔴 FAIL (F9-C-01) |
| Decision gates calibrated to CMP | 🔴 FAIL (F9-H-01) |
| P5 2-wk forward test (valid evidence) | 🔴 FAIL (F9-C-02; restart required) |
| Audit SHA-256 chaining | 🟡 FAIL vs CMP text (F9-M-01) |
| Latency gates enforced | 🟡 FAIL (F9-H-02 decision) |
| Branch protection | 🟡 FAIL (F9-M-02) |

**Minimum hard requirements before LIVE:** F9-C-01 → F9-H-01 → F9-C-02 (+14-day re-run PASS) → F9-H-04 → F9-H-03/H-05 → F9-M-01 → F9-M-02 → F9-H-02 decision recorded → Telegram kill-switch verification event in the P5 run log.

## 16. Module-by-Module Review

| Module | Cover | Verdict | Notes |
|---|---|---|---|
| trailing_stop.py | 93.2 % | ✅ | ratchet + SL-M emission exercised; default OFF (F9-L-02) |
| options.py / options_math.py | 95.2 % / ~88 % | ✅ | hand-rolled BS math (ADR-0004) |
| trade_decision.py | ~87 % | ✅ | routing success/disabled/error; queue lifecycle; persistence |
| orchestrator.py | 82.6 % | 🟠 | 5 producers; 8 s window design (F9-H-02); as_of_date not passed (F9-H-04) |
| rules.py | high | 🔴 | IV-rank math broken (F9-C-01); thresholds elsewhere OK (VIX settings-derived) |
| strength.py | high | 🟠 | gate math correct; thresholds off-spec (F9-H-01); exclusion semantics ✅ |
| sentiment.py | — | 🔴 | producer dead in prod (F9-H-03); P3 spec absent (F9-H-05) |
| strike_selection.py | 87.0 % | 🟡 | heuristic delta; no 2SD (F9-M-05) |
| backtest_sanity.py | 86.1 % | ✅ | weekly driver; floors restored |
| scheduler.py | 89.5 % | ✅ | single engine (ADR-0005) |
| alerts.py | 88.4 % | ✅ | /kill //resume gated |
| database.py (+async_additions) | ~81–89 % | 🟡 | dual-write atomic; chaining absent (F9-M-01) |
| utils/per_source_breakers.py | 100 % | ✅ | F8-L-01 closed |
| ta.py (numba) | 86 % | ✅ | |

## 17. Dependency Overview

| Item | State | Verdict |
|---|---|---|
| Manifest sync | check_deps_sync PASS (gate-enforced) | ✅ |
| `ta` lib | dropped (ADR-0003, numba rationale) | ✅ recorded |
| py_vollib | hand-rolled migration (ADR-0004) alongside | 🟡 recorded deviation |
| pip-audit | 0 vulns live | ✅ |
| npm artifacts | gone from tree post-purge | ✅ |
| External integrations | OpenAlgo REST (ANALYZE default), Telegram, 3 RSS feeds (bloombergquint removed, F8-L-05 closed), INDIAVIX quote | ✅/🟡 (intake decision F9-M-03) |

## 18. Prioritized Improvement Roadmap — SEQUENTIAL STEP-BY-STEP USER GUIDANCE (APPROVED 15Sep2026)

> Execution protocol per item (non-negotiable): BUILD → IMPLEMENT → INTEGRATE → REFACTOR → OPTIMIZE → VERIFY → IDENTIFY → ROOT-CAUSE → FIX → TEST → RECHECK → FIX → RE-VERIFY → CONFIRMED & VERIFIED SUCCESS → COMPREHENSIVE SUMMARY. Each numbered step below is directly executable.

**STEP 0 — TODAY (15 min, independent):**
1. `gh api -X PUT repos/npmvlKP/LOATS13July2026/branches/main/protection` — required CI contexts, ≥1 review, dismiss-stale, include-admins. Save response JSON to `docs/audit-history/`. (F9-M-02)
2. Verify: GET branch-protection → 200; direct push → 403.

**STEP 1 — WAVE 1 · P0 (start immediately after Step 0):**
1. Branch `fix/fr9-wave1-ivrank` from `main`.
2. **TODO-1 (F9-C-01):** build IV-series store (symbol+as_of_date keyed, chain-IV source) → rewrite `calculate_iv_rank` as true IV rank over 252-day series → kill the silent 0.5 fallback (TODO-9 folds in: loud `insufficient_history` blocks BOTH directions + audit row) → add the 5 property/boundary/replay tests → run rules/strength/e2e suites.
3. **TODO-13 (F9-H-01):** set `composite_strength_threshold=0.6`; lift `opposition_threshold` into Settings at `0.4`; update pinned tests with CMP citations; add conformance test.
4. **TODO-2 (F9-C-02):** stop supervisor PIDs 22072/22088 → archive `reports/p5_forward_test_*.json*` to `docs/audit-history/` marked INVALID-EVIDENCE → add instance-id/flag instrumentation at enable/cycle/route → engine single-construction registry → self-verifying ROUTE-vs-runlog canary → DB-derived counter reconciliation.
5. Run FULL gate battery: deps-sync, ruff check+format, isort, flake8, mypy strict, bandit, pytest+cov (≥80; floors), health check 32/32, pip-audit. All-green → merge via PR.
6. **Restart the 14-day P5 span** (`run_p5_forward_test.py --ack-live-endpoint`); verify within the first decision cycle that a ROUTE row carries `routing_enabled:true`; include the Telegram kill-switch verification event. (Completion of the span is the P5 gate — day 0 starts here.)

**STEP 2 — WAVE 2 · P1 (opens only after Wave 1 all-green):**
1. **USER DECISION FIRST — TODO-3 (F9-H-02):** choose (a) sub-100 ms hot loop via producer decoupling + last-known-good snapshots, or (b) ADR-amended measured budget (cycle P99 ≤ 250 ms hot; producers ≤ 8 s async; strike < 5 ms; trail < 1 ms). Either way: CI benchmark gate + health-check compliance floor.
2. **TODO-4 (F9-H-03):** URL-TTL article cache → background extraction → last-known-good producer (`degraded` tagging) → per-source liveness alert (>15 min during REGULAR).
3. **TODO-14 (F9-H-05):** bounded `sentiment_score` Field(ge=-1, le=1) → 4 h half-life decay → 70/30 weight scaffold (news 1.0; social leg ADR-deferred, never fabricated) → property tests.
4. **TODO-5 (F9-H-04):** pass snapshot-derived `as_of_date` at `orchestrator.py:1552-1561`; persist on decision + ROUTE row; tests per finding.
5. Gate battery → merge.

**STEP 3 — WAVE 3 · P2:**
1. **TODO-15 (F9-M-05):** delta band [0.50, 0.60] + sell-side 2σ (consistent units) + OI confirmation filter + boundary tests.
2. **TODO-6 (F9-M-01):** `previous_hash` column + `sha256(entry||prev)` + link-walking verifier + tamper tests + grandfathered migration.
3. **TODO-8 (F9-M-03):** USER DECISION — audited-attempt semantics (ADR) vs intake endpoint; update the P5 verifier accordingly. **RESOLVED 18Sep2026:** option (a) — ADR-006 Am.7, PR #56.
4. TODO-9 acceptance check inside TODO-1's RE-VERIFY record.

**STEP 4 — WAVE 4 · P3:** TODO-10 (warning thresholds), TODO-11 (trailing enable for supervised runs), TODO-12 (store hygiene + insert-time source guard), TODO-16 (kill-switch states or ADR), TODO-17 (CMP supersession register ADR).

**P5 GATE (after Waves 1+2):** 14-day span → `verify_p5_forward_test.py` PASS (≥14 d, 0 unhandled exceptions, routing enabled & attempted, Telegram kill-switch verified). **Go/No-Go LIVE:** per §15 minimum requirements. ANALYZE-mode demo may continue throughout.

## 19. Executive Summary

**The project is STILL not built strictly per `LOATS-CMP-13July2026.txt` — but this is the closest of the nine reviews, and for the first time the residual gap is precisely enumerable and sits in strategy math and evidence integrity, not process.** The wave since FR8 (post-purge, PRs #24–#42 at HEAD `57b77a0`) genuinely cured every FR8 Critical/High: 5 enum-tagged producers with a real-producer e2e (chain live-probed passing at 0.714), repo at 419 tracked files with CI hygiene guards, Rule-7 per-order persisted at the modify boundary (live-probed fail-closed), single signal engine, full 10-module floor map genuinely met, suite at 1,841/88.93 %, every §7 gate green simultaneously, and — a first — the verifiers fail their own run honestly. What this review's clause-by-clause pass newly exposed: the IV-rank function has been saturated at 100.0 since go-live (BUY unreachable; decisions are fallback artifacts), the decision-gate thresholds silently loosened to 0.5/0.6 against CMP's 0.6/0.4, P3's ensemble/decay/bounds were never built and the sentiment producer has been dead since 13Sep, `as_of_date` is plumbed but never passed, the "SHA-256 chain" remains self-hash only, the cycle-latency gate was abandoned de facto (0/816 compliant), and the P5 forward test — day 8 of 14 — is accruing invalid evidence (routing enabled by the supervisor, disabled at the router). Verdict: **NOT READY for live capital; ANALYZE-mode demo only.** Cure order: TODO-1 → TODO-13 → TODO-2 (restart P5) → then Waves 2–4 as sequenced in §18. **No false-readiness record this wave — keep it that way.**

## 20. Architecture Overview

```
src/loats/                              # flat package (38 files, mypy-strict clean)
├── main.py / initialization.py         # TradingSystem lifecycle: init → metrics :8001 → db(+audit verify)
│                                       #   → alerts/scheduler → orchestrator+scheduler start →
│                                       #   shutdown: drain(5s) → scheduler → alerts → async_close_all
├── lazy_settings.py + utils/lazy_singleton.py   # credential-free imports, fail-closed runtime
├── config/settings.py                  # pydantic v2; CMP values (lot 25, mods 25, 5/3, OPS 3,
│                                       #   ±0.05, ANALYZE default, routing flag default OFF,
│                                       #   producer_window 8.0 s)  ← thresholds drift F9-H-01
├── orchestrator.py                     # cycle @1 Hz: gather(TA‖SENT‖VOLATILITY‖PRICE_ACTION‖
│                                       #   OPTIONS_FLOW‖MARKET-DATA) under producer window →
│                                       #   VIX set → CMP strategy step → trailing driver
├── strength.py                         # 7-member enum; alias map; per-signal unknown exclusion;
│                                       #   diversity = unique/7 ≥ 0.5; weights incl. price_action 0.2
├── rules.py                            # session lifecycle; IV/ADX/VIX gates (BUY<30/>25/<15;
│                                       #   SELL>40/<25/>15; VIX symmetric fail-safe);
│                                       #   calculate_iv_rank ← F9-C-01; Rule-7 reserve/release
├── trade_decision.py                   # decision workflow; bounded queue; ROUTE audit row;
│                                       #   routing flag (default OFF; enable/disable methods)
├── openalgo.py                         # sync+async clients; kill switch; CBs (modify-no-retry);
│                                       #   Idempotency-Key; OPS limiter 3/s; Rule-7 gate at
│                                       #   BOTH modify_order entries (reserve→call→release)
├── database.py (+async_additions)      # sqlite3 WAL + aiosqlite pool; modification_counts table;
│                                       #   audit dual-write JSONL+row atomic; self-hash only (F9-M-01)
├── sentiment.py / rss_validation.py    # 3 feeds; startup gate + live drift; newspaper4k inline (F9-H-03)
├── ta.py (numba Supertrend) / options.py + options_math.py / strike_selection.py / sizing.py (2 %)
├── trailing_stop.py (ratchet, SL-M) / backtest_sanity.py (weekly walk-forward) / scheduler.py (single engine)
├── alerts.py (Telegram /kill //resume, admin-gated) / metrics.py (:8001 stdlib server)
└── utils/ (cache, circuit_breaker, per_source_breakers, connection_pool, payload_builder,
            rate_limiter, resilience, retry, lazy_singleton)

scripts/  run_p5_forward_test.py (supervisor: enable routing, resume baseline math, writer-claim
          single-writer guard, Windows image-name handling) · verify_p5_forward_test.py (grader) ·
          fr7_health_check.py (32 checks) · check_per_module_coverage.py (10-module FR floor map) ·
          benchmark_performance.py (unenforced)
data/     loats.db (WAL; signals/audit/decisions/modification_counts) · audit.log (JSONL dual-write)
reports/  p5_forward_test_*.json(+.claim) — current span INVALID-EVIDENCE (F9-C-02)
```

**Wave deltas (live-verified):** history purged via filter-repo; 5-source production emission; real-producer e2e; Rule-7 persisted boundary gate; per-source breakers wired; ADRs 0005–0015 added; P5 supervisor + honest grader.

## 21. Reverse Engineered Data Flow

```
              ┌──────────── orchestrator cycle @1 Hz (producer window 8.0 s) ───────────┐
              │ _execute_ta_analysis ──────────▶ Signal(source="ta")                   │
              │ _execute_sentiment_analysis ───▶ Signal(source="sentiment")  ← DEAD     │
              │ _execute_volatility_analysis ──▶ Signal(source="volatility")           │
              │ _execute_price_action_analysis ▶ Signal(source="price_action")         │
              │ _execute_options_flow_analysis ▶ Signal(source="options_flow")         │
              │ _execute_market_data_update ──▶ quotes/positions/funds → db            │
              │                                 └▶ _fetch_cached_vix → set_vix_level   │
              └──────────────────────────┬─────────────────────────────────────────────┘
                                         ▼
        db.async_get_latest_signals(NIFTY, limit=10, 5-min window)
                                         ▼
        strength.validate_signal_sources (per-signal unknown exclusion, loud warn)
          ├─ Gate 1: ≥3 unique known sources        ✅ live (4–5 sources persisting)
          └─ Gate 2: diversity = unique/7 ≥ 0.5     ✅ live (5/7 = 0.714)
                                         ▼
        composite strength ≥ threshold   ← 🔴 0.5 vs CMP 0.6 (F9-H-01)
        opposition block > threshold     ← 🔴 0.6 vs CMP 0.4 (F9-H-01)
                                         ▼
        rules.apply_gating_rules  ← 🔴 calculate_iv_rank ≡ 100.0 (F9-C-01):
          BUY  needs iv_rank<30  — unreachable (527/527 live rejects at 100.0)
          SELL needs iv_rank>40 ∧ ADX<25 ∧ VIX>15 — evaluated but never jointly true
          VIX None/stale ⇒ both blocked (symmetric fail-safe ✅)
                                         ▼ (1,542 decisions to date = fallback artifacts)
        position limits (5/3) → 2 % fixed-frac sizing (cost+margin aware) →
        trailing init (driver default OFF) → hist VaR → TradeDecision
          → persist (as_of_date NULL ← F9-H-04) → ROUTE audit row
          → route_to_analyzer: 🔴 flag reads FALSE inside P5-enabled windows (F9-C-02);
             enabled path ⇒ POST /api/v1/analyze (intake 404 by design — F9-M-03)
                                         ▼
   Order path: place_order → kill-switch → rate limiter (3/s, live-probed) → CB open-check
     → _request(Idempotency-Key) → OpenAlgo REST (ANALYZE)
   modify_order (SL-M ratchet): kill-switch → CB-no-retry → Rule-7 reserve (per-order,
     persisted, 26th raises) → broker call → release-on-failure (budget preserved)
   Ratchet events + routing outcomes → audit (JSONL+row; self-hash only ← F9-M-01)
```

---

## Appendix — FR8→FR9 disposition (condensed) & disclosures

**FR8 cured (live-verified this session):** F8-C-01 chain reachability ✔ · F8-C-02 repo hygiene (10,411→419; filter-repo; CI guard) ✔ · F8-H-02 Rule-7 ✔ · F8-H-03 single engine ✔ · F8-H-04 floors (full map + guard) ✔ · F8-M-01…07 ✔ · F8-L-01 per-source breakers ✔ · F8-L-05 bloombergquint ✔. **Still open from FR8:** as_of_date (→ F9-H-04) · P1 latency (→ F9-H-02) · branch protection (→ F9-M-02).

**Disclosures:** (1) Reviewer's live Rule-7 probe wrote two rows (`ORD-1`,`ORD-2`) into `data/loats.db.modification_counts`; deleted immediately with before/after captured — no other data, code, or tracked file modified; this file is the only artifact written (untracked root; relocate to `docs/audit-history/` before release). (2) **Not enough evidence (stated, not speculated):** root-cause mechanism of F9-C-02's flag divergence (instrumentation will settle it); broker-side Idempotency-Key honoring; `security.yml` weekly run results; attribution of the 02:05Z Enabled→Disabled 7 ms pair. (3) Suite facts: 1841 / 1 skipped / 0 failed / 88.93 % — the 1 skipped is declared, not silent.

*End of FR9 FINAL (sedrm protocol · 21 sections · APPROVED for Wave 1 + Step 0). Review-only deliverable; every recommendation is suitable for implementation only under the recorded approval and the STRICT LOATSEV protocol.*
