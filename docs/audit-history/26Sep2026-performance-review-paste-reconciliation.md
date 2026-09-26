# 26Sep2026 Paste Reconciliation — Performance Review Table (8 Rows; F9-H-02 / F9-L-01 / F9-L-02 Flags)

- **Issue ID:** 26Sep performance-review paste reconciliation · **Category:**
  Paste lag / mechanism misattribution / P5 span evidence · **Confidence:**
  Certain (every verdict below is a live probe at the recorded snapshot,
  not a transcript read).
- **Status:** RECORD ONLY — no production code changed by this wave. The
  ADR-0016 mid-span freeze binds every enforcement constant and the
  trailing-stop enablement until the 2026-09-30 checkpoint; the pasted
  table's three flagged rows are all already-dispositioned items (the
  deferred R-01 decision and the S-14/S-15 30Sep riders), and its six
  clean rows were re-verified in-tree.
- **Snapshot identity:** HEAD `f4a80ee` (PR #86 merged 2026-09-26), clean
  tree. Probes 2026-09-26T16:15–16:30Z (≈21:45–22:00 IST). CI run
  `36247737708` green at HEAD. Protection live-read: strict=true,
  10 required contexts, dismiss_stale_reviews=true, 1 approval — 7th
  consecutive clean field-by-field watch. P5 run
  `reports/p5_forward_test_20260924_080208.json` LIVE during probes
  (file mtime advancing through 21:49 IST): its INCOMPLETE verifier grade
  is the correct in-progress state, not a defect.

## 1. Verdict table (paste claim vs live evidence)

| # | Paste claim | Live evidence at HEAD `f4a80ee` | Verdict |
|---|---|---|---|
| 1 | Cycle < 100 ms ABANDONED de facto (8.0 s producer window; 0/816 compliant; avg 7.49 s, max 122.6 s) → F9-H-02 | F9-H-02 dispositioned by ADR-0016 (Accepted 2026-09-17): the budget decision is DEFERRED to the post-checkpoint wave as R-01 (due 2026-09-30) and the freeze binds every enforcement constant until then. The paste's 0/816 population is the 15Sep-era scrape; the register's R-01 row carries the fresher 21Sep scrape (count=2183, target_compliance_count=0) — same verdict, two snapshots newer. `producer_window_seconds=8.0` confirmed (settings.py:128-134) | STALE as an action item — CURRENT as the deferred R-01 decision |
| 2 | Strike < 5 ms: benchmarked, not CI-enforced; evidence `benchmark_performance.py` | Mechanism misattributed AND stale. (a) The fail-closed benchmark IS CI-wired: the `benchmark-perf` job runs `python scripts/benchmark_performance.py` with the exit-code contract (ci.yml:365-385, wired 17Sep per ADR-0016). (b) It is ADVISORY BY DESIGN — not a required context — until the R-01 decision lands; promotion is then a branch-protection context addition (ci.yml:352-364 comment; live protection read-back = 10 contexts, no benchmark-perf, exactly as designed). (c) `benchmark_performance.py` contains no strike budget: the 5 ms surface is the warn-only in-code budget (`strike_selection.py:219`, `orchestrator.py:1945`); the collector's 1ms/5ms defaults were retired (`performance_analyzer.py:26`) in favor of DB_GATE_MS=20 / ROUND_TRIP_GATE_MS=100 / TA_GATE_MS=80 | MISATTRIBUTED MECHANISM + STALE — advisory-until-R-01 is the registered design, not a gap |
| 3 | Trail < 1 ms: benchmarked, not CI-enforced; 93.2 % covered; default OFF (F9-L-02) | `enable_trailing_stops: bool = False` is risk-off BY DESIGN (settings.py:135-141). F9-L-02 = supersession row S-15, staged as the 30Sep rider (run-log pin + SL-M fixture); the rider deliverable is genuinely still pending — zero `Rule7ModificationLimitError` hits in `tests/test_trailing_stop*.py` at HEAD. No in-code trail timing surface exists; the < 1 ms number is R-01 amendment option (b) framing (RISK-REGISTER:236), deferred with it | STALE as an action item — CURRENT as the S-15 30Sep rider |
| 4 | Producer window semantically sound: both timeout AND exception paths cancel all producers; 50 ms settle grace (ADR-0007) | Timeout branch cancels and settles (`orchestrator.py:599-609`); exception branch same (`:634`); `_settle_cancelled_producers` helper at `:166` bounds the settle so every producer `finally` block completes and producers never outlive the cycle. ADR-0007 | CURRENT — confirmed |
| 5 | SQLite: WAL; dual-write JSONL+row; busy_timeout=30 s; aiosqlite pool + to_thread | WAL PRAGMA (`database.py:107`, set at `:257`); `busy_timeout=30000` (`database.py:111`); audit JSONL dual-write (`database.py:144`, `:177-180`); async pool with `busy_timeout=60000` (`utils/connection_pool.py:41`) plus `asyncio.to_thread` paths (`database.py:2885`, `:2914`) | CURRENT — confirmed |
| 6 | Caches: thread-safe TTL; sub-µs hits; VIX TTL-cached | TTL cache in-tree (`utils/cache.py`); cache latency benchmarked (`tests/test_performance_benchmarks.py::test_cache_latency`, 1 ms measurability floor); VIX TTL-cached (`openalgo.py`, `orchestrator.py`). The "sub-µs" figure is paste-era folklore — no budget claims it; the measured floor the repo pins is sub-millisecond | CURRENT — confirmed (sub-µs wording unattributed) |
| 7 | NumPy/numba: vectorized indicators; numba Supertrend | `ta.py:18` conditional njit import with cache-support probe (`:27-30`), Supertrend njit decorator (`:57-67`); Supertrend perf benchmark scales to 20k points (`tests/test_performance_benchmarks.py::test_supertrend_performance`) | CURRENT — confirmed |
| 8 | Log noise: 10 MB/day rotation; ~13 k budget warnings (F9-L-01) | `RotatingFileHandler` `maxBytes: 10485760` (`loats_logging.py:104-106`). Budget-warning surfaces = the FIVE producer sites with pre-window constants (orchestrator.py:758 TA 0.03, :902 sentiment 0.04, :1045 volatility 0.03, :1217 price-action 0.03, :1369 options-flow 0.03 — all vs the 8.0 s design window) per the S-14 census erratum. F9-L-01 = supersession row S-14, staged as the 30Sep rider; the constants move only with the R-01 decision (freeze-bound) | STALE as an action item — CURRENT as the S-14 30Sep rider |
| — | Tail: no N² regressions; no new blocking I/O beyond the producer-window design | Consistent with the tree: producer fan-out is gather+wait_for with bounded settle; blocking DB work rides `asyncio.to_thread`; the 26Sep benchmark flakes (R-09/R-10/R-11) were gate/harness classes, all fixed fail-closed | CURRENT — confirmed |

## 2. Mechanism corrections (pin for future work orders)

1. **"benchmark_performance.py exists; no gate" is doubly wrong.** The
   gate EXISTS in CI (`benchmark-perf`, exit-code contract, wired
   2026-09-17). What is absent is branch-protection ENFORCEMENT
   (advisory), and that absence is ADR-0016's registered promotion
   deferral bound to the R-01 decision — not an oversight and not open
   work. Any future wave reading this row as "wire the benchmark into
   CI" would re-do work landed 17Sep.
2. **`benchmark_performance.py` is not the strike/trail venue.** Zero
   strike/trail budget surfaces live in that file at HEAD. Future S-14 /
   S-15 / R-01 work orders must cite the real surfaces:
   `strike_selection.py:219` + `orchestrator.py:1945` (warn-only 5 ms),
   `orchestrator.py:2188` (trail < 1 ms budget docstring), and the
   collector constants (`collect_p1_phase_gate_evidence.py`:
   DB_GATE_MS=20, ROUND_TRIP_GATE_MS=100, TA_GATE_MS=80) — never
   line numbers in `benchmark_performance.py`.
3. **Population-freshness:** the paste's `0/816` cycle-compliance
   evidence is the 15Sep-era scrape. The in-tree R-01 row carries the
   21Sep population (`count=2183`, `target_compliance_count=0`). Cite
   the fresher numbers; the verdict (0 % compliance, decision deferred)
   is unchanged.

## 3. Live-system observations during probes

- P5 span `p5_forward_test_20260924_080208.json` is LIVE (mtime
  advancing through 21:49 IST during the probe window); grade INCOMPLETE
  is correct-in-progress. The two in-run operational deadlines stand
  unchanged: kill-switch event already verified in-run (26Sep 12:39Z);
  `routed_decisions` still 0 — the R-12 decisional-leg deadline
  (2026-10-08) governs. No new code action arises from this paste.
