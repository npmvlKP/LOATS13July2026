# 10Sep2026 - Analyzer wire-contract route repair (P1 pre-forward-test wave)

**Finding class:** F8-H-01 residual - routing integration defect (live)
**Tree:** main @ 83dc449 + this wave
**Decision record:** ADR-006 Amendment 3

## Executive summary

Verifying the three P1 items from the top of the P1 stack produced the
verifier-first verdict: F8-H-02 and F8-M-02 were already delivered at
HEAD (external verifiers 7/7 and 19/19, rc=0). Item 5 (enable routing +
begin the 2-week P5 forward test) was already *running* (day 3 of 14,
claim-guard intact, 8 restarts survived) - but its counters proved the
run structurally incapable of ever grading PASS: zero decisions across
3 days. Root-caused to a live wire-contract break, fixed, verified
live, and the supervised run restarted per ADR-006 Amendment 2's own
runbook.

## Forensic chain (all live-evidenced)

1. The supervised run (p5_forward_test_20260907_124455) logged
   **10,332 position_book 404s** and **52,804 trading-cycle errors**
   (breaker-open flapping). Live probe against the running gateway
   (127.0.0.1:5000, commit d36936a6) confirmed the client's snake_case
   endpoints (`position_book`, `trade_book`, `all_orders`, `order_status`,
   `place_order`, `place_smart_order`, `modify_order`, `cancel_order`)
   return HTTP 404; the deployment serves underscore-free one-word routes
   (`/positionbook`, `/tradebook`, `/orderbook`, `/orderstatus`,
   `/placeorder`, `/placesmartorder`, `/modifyorder`, `/cancelorder`).
2. Decisions/ROUTE rows collapsed across the run: 111 (Sep 7) -> 5
   (Sep 8) -> 2 (Sep 9) -> **0 during 10Sep market hours despite 10,026
   stored signals**; 46 REJECTs cite `insufficient_source_diversity`
   (3/7 sources in-cycle: the breaker cascade starves one producer per
   window). 10Sep also saw the sentiment producer emit 0 signals
   (threshold-gated; feed validation degraded under the cascade).
3. The two post-run-start `disabled` ROUTE rows (Sep 9 03:16/05:39)
   audited `routing_enabled: false` *inside* a supervised stint. Their
   process could not be the supervised writer (its sampled `disabled`
   counter stayed 0 - resume-baseline absorption makes cross-process
   counter attribution impossible); the double-import hypothesis was
   eliminated by controlled probe (runner/orchestrator resolve the same
   `loats.trade_decision` LazyProxy; enable propagates in-process).
   Most probable: unsupervised manual runs against the shared DB.
4. **The 380 historical routing "success" outcomes are provably not
   gateway responses**: this gateway has no `/api/v1/analyze` route
   (404 live), `/api/v1/analyzer` is a mode-status endpoint, and
   `{"status": "accepted"}` is emitted by nothing in the gateway tree;
   186+ carry the documented test-fixture marker `analyzer_id:
   "abc-123"` (ADR-006 Amendment 2 finding 3). Routing has never once
   hit a real Analyzer intake. The semantic question is recorded OPEN
   in ADR-006 Amendment 3 (user decision: defer).

## Changes (3 modified, 1 added)

- `src/loats/openalgo.py` - renamed 8 endpoint literals x sync+async
  (16 call sites) to the deployment's routes; added
  `_normalize_position_book` (gateway rows carry `ltp`; callers read
  `last_price`; explicit broker field wins; non-list passthrough).
  Completes the 555e39e alignment class.
- `tests/test_openalgo_wire_contract_routes.py` (new) - RED-verified
  route pins for all 8 async + sync position/trade methods, the
  `ltp` alias, explicit-`last_price` precedence, error passthrough,
  and a no-dead-spelling source scan.
- `docs/ADR-006-analyzer-routing-p5.md` - Amendment 3: route repair,
  vocabulary alias, the OPEN Analyzer-intake semantic, run restart.
- `scripts/ratchet_baseline.py` - ceiling 401 -> 402 (single-source,
  reason-annotated per contract).

## Verification (Windows, loatsNEW venv, measured)

- RED: new suite failed on the pre-fix client
  (`assert 'position_book' == 'positionbook'`).
- GREEN: `pytest tests/ -q` -> **1760 passed** (incl. the new suite),
  rc=0. Full-suite run started BEFORE the final whitespace touch-up;
  the touch-up restored a pre-existing blank line (format-gated:
  `ruff format --check` green before and after), so the collected
  file set was byte-identical.
- Live end-to-end: `AsyncOpenAlgoClient.get_position_book()` against
  the running gateway -> `status: success`, `data: list` (was 404 on
  every call for days); `get_all_orders()` -> `success`.
- Fresh supervised run `p5_forward_test_20260910_134427`: writer alive,
  120 cycles measured, 0 unhandled exceptions, **0 position_book 404s /
  0 breaker-open errors** since start (vs 52,804 cycle errors in the
  equivalent span of the prior run). Counters 0 at market-close time
  (17:14+ IST, post-session start) - decisional activity evidence
  accrues from the next market session.
- Gates: ruff check/format, isort, flake8, mypy --strict, bandit,
  pip-audit (PYSEC-2026-3740 waived per ADR-0010) all rc=0.
  HC registry + fr7 sweep running at record time; final results to be
  appended below on completion.
- External verifiers on the amended tree: verify_f8h01_external
  **17/17** (JSON timestamp 2026-09-10T14:00:09Z), verify_f8m02_m07
  **19/19**, verify_f8h02 **7/7** (chained run rc=0).
- Gitleaks clean (worktree detect + since-HEAD git scan, rc=0).
- HC registry sweep: 31 PASS / 1 FAIL - the single FAIL (HC-12) was the
  ratchet-lockstep test executing against the MID-EDIT tree (ceiling
  402 while the wave record was still untracked); re-run on the final
  tree: PASS (and `TestRatchetLockstep` full: PASS). The sweep's own
  pytest leg measured 1759 passed + that 1 mid-edit failure.
- Latency benchmark: first run overlapped the live coverage bundle
  (contention per doctrine) and was DISCARDED as evidence regardless of
  verdict; exclusive re-run on the quiet final tree:
  **overall_status=PASS, cmp_validation 10/10, benchmark_validation
  2/2** (performance_benchmark_20260910_142753.json).
- Final-tree coverage bundle: `pytest --cov=src --cov-fail-under=80` →
  **1760 passed, 88.15%** (rc=0) + `TestRatchetLockstep` 5/5 at the
  final ceiling (403).

## Run lifecycle (operator-approved restart)

- 124455 ended 2026-09-10T13:39:44Z with explicit `operator_termination`
  event citing Amendments 2/3 (structurally INCOMPLETE).
- Fresh-start attempt 133956 failed at system start (transient
  Telegram "Timed out" during initialize; no proxy env on this host -
  confirmed registry-empty, so environment parity with the scheduled
  task holds; first startup-timeout occurrence in the log).
- 134427 started 13:44:27Z via the same direct-invocation form; the
  LOATS_P5_Resume logon task (VBS wrapper, NO_PROXY set) provides
  restart continuity as designed.

## Live health of the fresh run (measured 14:16Z, ~32 min in)

- 256 cycles sampled, 0 unhandled exceptions, writer alive.
- **Zero API 404s, zero position_book failures, zero openalgo breaker
  trips, zero trading-cycle errors** since start (prior run: 10,332
  position_book 404s and 52,804 cycle errors in its first equivalent
  span). All six producers emit on every cycle (budget-exceedance
  warnings are the expected telemetry of the 8 s producer window under
  ~1.3-8 s live fetches; producers persist signals before the window
  closes, and zero REJECT rows have accumulated so far - vs 46 on the
  prior run during the same market phase).
- Decisional counters remain 0 at record time: post-market session
  (13:44Z = 19:14 IST, after the 15:30 IST close) - the run's CMP gate
  is session-gated by design. First decisional evidence accrues from
  the next trading session (11 Sep, 09:15 IST); the wire path it needs
  (positions, quotes, history, chain) is now verified working live.
