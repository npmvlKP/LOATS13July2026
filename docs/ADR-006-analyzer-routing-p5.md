# ADR-006: Analyzer Routing Default OFF vs CMP P5 (F8-H-01)

**Status:** Accepted
**Date:** 2026-09-02
**Finding:** F8-H-01 (CMP Conformance, P5) — High conformance / Low capital safety

## Context

CMP phase gate P5 mandates, unconditionally: *"route ALL TradeDecisions to
Analyzer Mode."* The repository ships `Settings.analyzer_routing_enabled =
False` (`config/settings.py`), and `TradeDecisionEngine._do_route_or_disable`
terminates every decision in an audited `{"status": "disabled"}` outcome
when the flag is off.

The OFF default was itself a mandated safety correction: TODO-13 (HC-19)
removed the earlier default-ON **fabrication** — F7-H-01 documented
`analyzer_routing_enabled = True` returning a made-up
`{"status": "success", "analyzer_response": {"status":
"QUEUED_FOR_ANALYSIS"}}` after an `asyncio.sleep(0.1)` stub, with no HTTP
call. Turning the flag OFF by default killed that fabrication class.

F8-H-01 then observed the remaining gap: with routing off, the P5 2-week
forward test measures nothing, so the P5 gate stays open — a **documented,
deliberate deviation** from the unconditional P5 wording.

## Decision

1. **The production default stays OFF.** It is the runtime kill path
   (capital-safety direction) and the guard against default-on fabrication.
   Two gates enforce it: `scripts/verify_hc_registry.py` (AST check) and
   `scripts/fr7_health_check.py` HC-19. `ANALYZER_ROUTING_ENABLED=false` is
   documented in `.env.example`.

2. **Deviation recorded here (this ADR) and in README.** Until P5 closes,
   conformance reports cite this ADR as the tracking artifact.

3. **The closing step now exists and is runnable:**
   - `scripts/run_p5_forward_test.py` — supervisor that enables routing
     only for the supervised run (via `enable_analyzer_routing()`), runs
     the real `TradingSystem`, and appends a run log to
     `reports/p5_forward_test_<ts>.json`. Live runs require
     `--ack-live-endpoint`; `--dry-run` exercises the enable path without
     HTTP.
   - `scripts/verify_p5_forward_test.py` — grades run logs against the P5
     criteria: ≥14-day span, zero unhandled exceptions, routing enabled.
     Exit 0 iff PASS.

4. **Every routed decision now leaves a ROUTE audit row.** F8-H-01's
   Recommended Test (1) requires "an audit row with routing outcome exists
   per decision." Root-cause fix in `trade_decision.py`
   `_persist_routing_outcome`: the previous code probed for a nonexistent
   `db.async_record_trade_decision` (dead branch — only the private
   one-arg `_async_record_trade_decision` exists), so routing outcomes
   were never audited. The fix writes a dual-write (SQLite + JSONL,
   SHA-256-chained) `ROUTE` audit row via the canonical `async_log_audit`
   for **every** outcome — success, disabled, and error — and persists the
   `trade_decisions` row when missing (idempotent with the orchestrator's
   pre-persist).

5. **`get_decision_status` no longer fabricates.** It returned a hardcoded
   `{"status": "PROCESSED", "analyzer_status": "ANALYZED"}` mock for any
   id — the exact F7-H-01 fabrication class. It now reads the real
   `trade_decisions` row via `async_get_trade_decision` and returns
   `NOT_FOUND` for unknown ids.

## Consequences

- P5 remains formally open until the 2-week supervised run completes and
  `verify_p5_forward_test.py` grades PASS. TODO-25 evidence continues to
  record P5 as BLOCKED until that run starts; once it starts, the run log
  becomes the phase-gate evidence.
- `enable_analyzer_routing()` / `disable_analyzer_routing()` remain the
  runtime kill path, unchanged.
- Existing consumers of `get_decision_status` see `NOT_FOUND` for unknown
  ids and persisted statuses otherwise; the only observable behavior
  change is the removal of invented state.
- Latent-defect removal (ROUTE audit rows, real status) requires no
  config change and is covered by
  `tests/test_analyzer_routing_integration.py` +
  `tests/test_p5_forward_test.py` and graded by `scripts/eval_f8h01.py`.

## Verification Model (the F8-C-01 lesson)

Per ADR-005: a green gate is only evidence if the gate measures the thing
the mandate cares about. The eval harness `scripts/eval_f8h01.py` grades
the ten observable behaviors from the finding (before: 4/10 → after:
10/10), and the external verifier `scripts/verify_f8h01_external.py`
re-checks the same facts from a clean process without the test suite.

## Amendment (2026-09-05, P5 evidence integrity: measured activity + freshness)

Preparing the supervised run exposed an evidence-integrity shortfall in
the P5 machinery itself: the supervisor wrote only literal zeros for
``cycles_completed``/``counters`` (dead schema — the ~130 dry-run smoke
logs on disk were grade-identical to a 2-week live run), and the
validator's PASS criteria ignored activity entirely, so a 14-day run in
which nothing ever routed would still grade PASS.

1. **Routing counters are live engine state.**
   ``TradeDecisionEngine.routing_counters`` (success / disabled / error)
   increments only when a routing call actually resolves, exposed via
   ``get_routing_stats()`` — the same zero-fabrication standard as the
   ROUTE audit rows (§4).

2. **The supervisor samples instead of asserting.**
   ``run_p5_forward_test.py`` captures baselines at run start and folds
   live deltas (``orchestrator.cycle_count``, routing counters, kill-switch
   state, ``system.running``) into the run log every 60 s via
   ``_sample_live_activity`` / ``_supervise_live``. Supervision ends on
   duration, system-task exit, or gate-pass detection (re-grading the log
   "pretend-ended" via the official validator, so detection can never
   drift from the grader).

3. **PASS requires measured activity.** When a run log carries
   ``cycles_completed``/``counters``, zero total activity is a hard FAIL
   ("run measures nothing"); logs without those fields (legacy) grade
   unchanged. ``last_sampled_at`` yields a reported data-freshness delta.

4. **``--status`` reports measured activity, freshness, and the live
   verdict**, so an operator can watch a multi-day run without hand-parsing
   JSON.

5. **Restart continuity: ``--resume`` (2026-09-05).** A 14-day supervised
   run cannot assume the host stays up; a single reboot must not destroy
   the span. ``--resume`` continues the newest ongoing live run log (or the
   ``--run-log`` target) in a fresh process: ``started_at`` is preserved,
   ``restarts`` is incremented, routing is re-enabled, and the new
   process's counters are shifted via ``_effective_resume_baseline``
   (baseline = max(live − logged, 0)): seamless continuation when live ≥
   logged, floor-at-live when a counter reset happened across the restart
   — a drop in the log, never inflation. Refused (exit 2) for dry-run or
   ended logs: resuming either would fabricate a span.

6. **Exit-code contract.** ``run_p5_forward_test.py`` previously called
   bare ``main()``, discarding its return value — a failed live run exited
   0 to Task Scheduler. The entry point now ``sys.exit(main())``.

## Amendment 3 (2026-09-10, wire-contract route repair; /analyze intake open)

Live forensics during the supervised run (124455) proved the client was
calling REST routes this deployment does not serve. Verified live
against 127.0.0.1:5000 (gateway commit d36936a6): the deployment's
/api/v1 routes are underscore-free one-word names (/positionbook,
/tradebook, /orderbook, /orderstatus, /placeorder, /placesmartorder,
/modifyorder, /cancelorder); the client's snake_case spellings returned
HTTP 404 on every call. The supervised run logged 10,332 position_book
404s; each market-data step's failure flapped the openalgo circuit
breaker open (52,804 trading-cycle errors logged), which cascaded into
every source breaker and starved the CMP funnel: zero decisions and
zero routing outcomes during 10Sep market hours despite 10,026 stored
signals.

1. **Route names aligned.** All 16 call sites (8 endpoints x sync +
   async) renamed to the deployment's routes. This completes the 555e39e
   alignment (which fixed quotes/history/optionchain but missed this
   class).

2. **Position-book vocabulary normalized.** The deployment's position
   rows carry ``ltp`` while the orchestrator reads ``last_price``; the
   client now aliases it per row (same pattern as funds/quotes).

3. **OPEN QUESTION (deliberately unresolved): the Analyzer intake
   semantic.** The gateway has NO decision-intake endpoint: POST
   /api/v1/analyze 404s on this deployment, and /api/v1/analyzer is a
   MODE STATUS endpoint (AnalyzerSchema takes only apikey; the service
   returns mode/logs-count). Analyzer Mode is an order-interception
   mode: when analyze-mode is on, order placement (/placeorder) is
   routed to the sandbox instead of the broker. Consequently the 380
   historical ROUTE "success" outcomes are provably not gateway
   responses: ``{"status": "accepted"}`` is emitted by nothing in the
   gateway tree, and 186+ carry the test-fixture marker
   ``analyzer_id: "abc-123"`` (ADR-006 Amendment 2 finding 3). With
   place_analyzer_request still posting to /analyze, a real routed
   decision resolves as an ``error`` outcome (HTTP 404) -- honestly
   counted, but not yet a conformant Analyzer intake. **The semantic
   mapping (real orders via /placeorder under analyze-mode vs a
   read-only status telemetry) is deferred to a later session and must
   be recorded here before the P5 gate can close.** Until then, the P5
   PASS criterion's "measured decisional activity" counts any resolved
   outcome (incl. the honest /analyze 404 errors), per Amendment 2 §3.

4. **Run restart ordered.** Per Amendment 2, the zero-decisional run
   124455 is structurally INCOMPLETE and was ended/restarted by the
   operator after this amendment's fixes were verified live.

Run logs written by the upgraded supervisor are the P5 phase-gate
evidence; dry-run smoke logs now grade INCOMPLETE/FAIL on span and (for
upgraded writers) would fail the activity requirement rather than
masquerading as live evidence.

## Amendment 2 (2026-09-07, forward-test integrity: the run measured a sterile loop)

Five days into the supervised live run (resumed through 7 restarts,
29,836 cycles, zero unhandled exceptions) a full forensic pass proved the
run **could never satisfy P5 regardless of span**, and that the activity
it did measure was partly spurious:

### Findings

1. **Producer-window starvation (P1, fixed).** The trading cycle spawned
   TA/sentiment/volatility/price-action/market-data producers inside a
   hard-coded **80 ms** window (``timeout=0.08``), then cancelled them
   (F8-M-02: producers never outlive the cycle). Live feed latencies are
   ~1.3 s per analysis — every producer was cancelled before it could
   persist a signal. Consequence chain: ``async_get_latest_signals`` →
   empty → "insufficient signals" every cycle → no TradeDecision is ever
   created → ``route_to_analyzer`` never runs → routing counters stay at
   zero for the life of the run. The supervised engine's own log
   confirmed it: zero ``Routing TradeDecision`` lines in 5 days. **The
   window is now settings-driven (``producer_window_seconds``, default
   8 s; ``PRODUCER_WINDOW_SECONDS`` in ``.env.example``).** The F8-M-02
   invariant is unchanged (both settle boundaries preserved — external
   verifier re-verified 19/19).

2. **Validator could grade a decisionless run PASS at 14 d (P1, fixed).**
   PASS required only span + cycles + zero exceptions. A run that never
   routed a single decision would have cleared the phase gate on
   cycle-count alone. **PASS now additionally requires measured
   decisional activity**: with ``counters`` present, all-zero
   success/disabled/error is a hard FAIL ("cycles alone do not satisfy
   P5"). Legacy logs without ``counters`` grade unchanged.

3. **Test-data contamination (P1, fixed).** Suite runs leaked into
   production data via the unpatched module-level ``db`` singleton:
   **186 production audit rows carry the test fixture's analyzer
   response** (``analyzer_id: "abc-123"``), and DB decision-burst
   timestamps match pytest run times, not the supervised cycle. The
   conftest now pins ``SQLITE_DB_PATH``/``AUDIT_LOG_PATH`` (hard
   override) to a private temp dir before any loats import, so the
   singleton is physically unable to bind production files under test.

4. **Run-log stub pollution (P3, fixed).** ``test_dry_run_creates_run_log``
   ran the real runner against the real ``reports/`` — ≈200 smoke stubs
   accumulated in the evidence directory. ``P5_RUN_LOG_DIR`` now
   redirects runner writes; the test uses it (temp dir per run).

5. **Counters were honest (root-caused, no fix needed).** The supervised
   engine never received a decision to route, so its zero counters were
   truthful — the falsity was in what the run would have proved. The
   wiring (proxy → instance → counters → ``get_routing_stats()``) was
   verified end-to-end by controlled probe (0 → 1 on a routed decision).

### Consequences

- The ongoing supervised run is **structurally INCOMPLETE**: it can never
  grade PASS (decisional criterion fails on its zero counters), and its
  cycles measured a starved loop. **It must be restarted** after this
  amendment ships: ``run_p5_forward_test.py`` resumes only ongoing logs,
  so the operator ends the current log (stop the supervisor task) and
  starts a fresh run (``--ack-live-endpoint``) once decisions are
  actually flowing. The 14-day clock restarts with the new run.
- ``verify_p5_forward_test.py`` exit codes unchanged; ``run --status``
  unchanged; the two F8-M-02 settle call-sites are byte-identical
  (external verifier 19/19 re-verified on the amended tree).
- Regression tests: ``tests/test_f8h01_fixes.py`` (13 cases) locks all
  four fixes.
- The decisional criterion is calibrated to **any** resolved routing
  outcome (success, disabled, or error all count): a healthy supervised
  run with routing enabled produces successes; the criterion exists to
  catch the zero-decisional class, not to grade outcome quality.
