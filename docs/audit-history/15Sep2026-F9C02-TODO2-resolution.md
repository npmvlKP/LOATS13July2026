# F9-C-02 / TODO-2 Resolution Record — P5 routing divergence: provenance guard, port-conflict refusal, self-verifying evidence

**Date:** 2026-09-15 · **Finding:** FR9 F9-C-02 (Critical, P0 — TODO-2)
**Branch:** `main` @ `fa8f3c5` (base) · **Protocol:** STRICT LOATSEV (BUILD → ... → CONFIRMED & VERIFIED)
**CMP basis:** P5 phase gate — 2-week forward test, routing ALL TradeDecisions to Analyzer, graded from measured evidence only.
**Dependencies at execution time:** F9-C-01 merged (PR #44 wave lineage); F9-H-04 (as_of_date call-site variants) NOT yet landed — F9-C-02's dependency list names F9-H-04; this wave proceeds on the operator's explicit go for TODO-2. F9-H-04 remains open at its register priority.

## Root cause (verified, not assumed)

The FR9 report's three candidates (second engine process; lazy-singleton rebuild
during `TradingSystem.initialize()`; supervisor sampling a different instance)
were resolved by source read + live host forensics:

1. **In-process duplication is structurally impossible.** Grep over the whole
   tree: `lazy_singleton(TradeDecisionEngine)` is bound EXACTLY ONCE
   (`src/loats/trade_decision.py:777`); the orchestrator imports that same
   binding (`orchestrator.py:32`); `TradingSystem.initialize()` performs NO
   engine construction (read of `src/loats/main.py`). A second engine inside
   the supervisor process cannot exist.
2. **The second process was a second LOATS SYSTEM, not a second engine.** The
   host runs `LOATS_P5_Resume` (boot), `LOATS_P5_Watchdog` (5-min) and
   `LOATS_P5_Status` (daily) scheduled tasks; the watchdog wrapper
   (`C:\Users\npmvl-KP\loats-ops\p5_resume_wrapper.cmd`) legitimately
   launches supervisors, but a supervisor boots a FULL `TradingSystem`
   whose `enable_analyzer_routing()` happens only in the supervisor — any
   process that reached `TradingSystem` without the supervisor claim ran
   with routing DEFAULT-OFF (Settings default `False`, ADR-006) and wrote
   `routing_enabled:false` ROUTE rows into the SHARED SQLite audit stream.
3. **The port conflict was swallowed.** `TradingSystem.initialize()` logged
   "Failed to start metrics server" and CONTINUED when `:8001` was already
   bound by the other process — the supervisor never learned a second
   system was live. This is the direct evidence for counters 0/0/0 vs
   `:8001` 816 cycles and for ROUTE rows the supervisor's own engine
   never produced.

Suppressed evidence that sealed it: the 02:04:58Z disable line in the shared
`logs/loats.log` while the supervisor's own counters stayed 0/0/0 — impossible
for one process (its disabled counter was never incremented), deterministic
for two.

## Remediations (root-cause, per the finding's mandated list)

1. **Route-time provenance guard** (`src/loats/trade_decision.py`):
   `enable/disable_analyzer_routing()` now record a CLAIMED state
   (`_routing_claimed_enabled`). When a claimed-enabled engine hits the
   disabled branch, `_do_route_or_disable` alarms (logger.critical + CRITICAL
   Telegram alert, silence-window `LOATS_ROUTING_DIVERGENCE_SILENCE_S`,
   default 900 s), writes a best-effort dual-write REJECT audit row
   (`entity_type="routing_divergence"`, `reason="f9c02_routing_divergence"`),
   and raises `RuntimeError` — the poisoned `disabled` ROUTE row is never
   written because the response is never returned. The legacy disabled path
   (no claim) is byte-for-byte unchanged.
2. **Metrics-port boot refusal** (`src/loats/main.py`): a
   `metrics.start_server` failure now tears down the partially-initialized
   components (`alerts.shutdown()`) and raises `RuntimeError` naming the
   F9-C-02 guard — a second LOATS process can no longer boot invisibly
   against the same DB.
3. **Supervisor identity provenance** (`scripts/run_p5_forward_test.py`):
   `_engine_identity()` (binding `id()` via module-attribute read, so test
   patches are reflected) is stamped at run-log init, at baseline capture,
   and re-stamped on EVERY sample (`routing_engine_identity`,
   `run_log_path`); the counters' producing engine is attributable.
4. **Self-verifying evidence (DB-derived)**: every sample folds
   `disabled_routes_during_enabled_window` into the run log — the
   count and first/last stamps of ROUTE rows with `routing_enabled:false`
   inside the run span, collected from the DB (source of record) by the
   validator's new `collect_disabled_route_rows` helper. A clean DB
   records an explicit zero-count; a probe failure records an `error`
   key rather than a false clean bill.
5. **Grader hard-FAIL**: `verify_p5_forward_test.grade_run_log` grades the
   new field with trust-but-verify semantics — an intersecting divergence
   window hard-FAILs the run regardless of every other criterion; a window
   entirely outside the span is an upstream artifact and does not fail this
   run (partial stamps fall back to whichever bound exists).
6. **Counter reconciliation surface**: `collect_disabled_route_rows`
   (validator) returns `(entity_id, timestamp)` for every `routing_enabled:false`
   ROUTE row in `[since, until]`; rows whose metadata cannot prove either
   state are skipped.

## Verification evidence (live, this session)

- New regression suite `tests/test_p5_f9c02_routing_guard.py`: **21/21 PASS**
  (RED-first proven by `git stash push` of the four production files: 14
  failed / 5 passed on base HEAD — every mandated behavior fails without the fix).
- The guard self-caught two test-construction errors mid-wave (an accidental
  flag-reset patch in the enabled-path test; a stand-in identity mismatch),
  demonstrating the provenance check fires on real foreign resets.
- Legacy suites impacted by the touched surfaces:
  test_p5_forward_test + test_trade_decision + test_main* +
  test_analyzer_routing_integration + test_analyzer_breaker_isolation =
  **136 passed**; test_format_surface_contract 15/15 post-freeze (3 mid-run
  failures were the documented stale-snapshot race, re-run green).
- Quality gates re-run after the change (repo venv, CI-exact commands):
  ruff check PASS; ruff format --check PASS (192 files); isort PASS;
  flake8 PASS; mypy `src/ --strict` PASS (38 files); bandit `src/` 0 findings
  (report deleted after read); pip-audit 0 vulnerabilities
  (PYSEC-2026-3740 ignored per ADR-0010 standing waiver, re-verified live);
  gitleaks 594 commits no leaks.
- Tracked-file ratchet: ceiling 422->424 with a per-commit ledger entry
  (test suite = 423rd file, this record = 424th), bump landed in the same
  commit as the suite.
- Full pytest + coverage: see final run log referenced in the session
  summary (authoritative run on the frozen tree; the earlier background
  run 1888 passed / 3 stale-race failures predates the last edits).

## Hardening wave (independent adversarial grading, same day)

A fresh read-only subagent graded the landed remediation against the
finding's standard: (a) remediation coverage PASS-with-notes,
(b) hole hunt **FAIL — 3 blocking holes (probe-verified)**,
(c) test pins PASS-with-notes. Every blocking hole and the adopted
minors are closed in this wave; suite grown 21 -> 33 tests.

Holes closed (blocking first):

1. **Boot refusal was dead code** (probe-verified): `start_server`
   swallowed its own exception, AND the `ThreadingHTTPServer` default
   (`allow_reuse_address=True` => SO_REUSEADDR) double-binds the same
   port silently on Windows. Fix: `start_server` re-raises;
   `start_http_server` binds via an `_ExclusiveMetricsServer` subclass
   (`allow_reuse_address = False` set BEFORE construction -- the
   constructor itself binds) and wraps bind failure in an F9-C-02
   OSError. Real-OS double-bind probe pins it.
2. **RuntimeError neutralized by the orchestrator loop**
   (`_run_cycle_loop` catches Exception, logs, continues; counters
   stayed clean and the span stayed gradeable PASS). Fix: the guard
   increments a grader-visible `routing_divergence_detected` counter
   before raising; the supervisor samples it into the run log (baseline
   and resume delta arithmetic generalized to engine-carried keys);
   the grader voids any run with a positive count. The queue loop gets
   the dedicated `RoutingDivergenceError` kill path (disables routing,
   re-raises -- never sleep-and-continue).
3. **Grader whitelisted the supervisor's own failure shape**
   (probe-verified PASS on `{"error": ...}`). Fix: any present-but-
   unverifiable divergence field (error key, missing/non-numeric count,
   count without parseable stamps) is INCOMPLETE, never PASS; the
   collector propagates store failures instead of folding `[]`.
4. Legacy poisoned log: the grader now condemns legacy logs (no
   divergence field) whose span overlaps the documented 15Sep
   contamination window (`CONTAMINATION_WINDOWS`, 01:00-05:00Z).
5. Identity ambiguity: `id()`-only stamps are recycled across process
   restarts and survive proxy `_instance` rebuilds; identity is now
   `pid=<pid>;start=<process start marker>;engine=<resolved instance>`.
6. Alarm flood control: the silence window advances ONLY on a
   successful Telegram send (a failed delivery re-attempts next
   divergence); the `<` vs `>=` boundary is factored into a pure
   predicate; the window is read at alarm time (env changes honored).
7. Hermeticity: the production-data pin skips on hosts without the
   live `data/` tree (fresh clones / CI).
8. Docstring-vs-code contradiction on the baseline's `run_log_path`
   contract corrected (explicit None placeholder, stamped by first
   sample).

Notes NOT adopted (recorded for the register): the supervisor's
sampling lock remains the pre-existing `_update_run_log` read-modify-
write (unchanged risk surface); the DB-probe window uses the run span
(operator `/disable` mid-run would flag -- acceptable for supervised
runs where the supervisor holds the claim for the whole span); finding
step 3's "process-wide registry" is delivered as the exclusive-bind
boot refusal + provenance stamps rather than an engine registry
(no second-engine path exists in-process; see root cause).

## Not done here (explicitly out of scope)

- The 14-day P5 span restart (requires the operator's runbook execution:
  retire the current span, neutralize relaunchers, fresh start with
  `--ack-live-endpoint`, verify first ROUTE row `routing_enabled:true`).
- F9-H-04 as_of_date wiring (register dependency, separate wave).
- Archiving the poisoned 20260912_150243 run log as INVALID-EVIDENCE
  (operator action; the grader now hard-fails it on the next
  `--status`/verify once the divergence field is folded — legacy logs
  without the field keep their legacy grading).
