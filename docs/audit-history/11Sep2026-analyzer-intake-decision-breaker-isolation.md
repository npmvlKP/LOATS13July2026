# Analyzer Intake Decision (Am4) + Routing-Failure Isolation + Continuity Watchdog - Wave Record

**Date:** 2026-09-11 (Asia/Calcutta)
**Wave:** P5 decisional-evidence prep (day 1 of the 14-day span): resolve the
ADR-006 Amendment 3 OPEN intake semantic, eliminate the routing-failure ->
shared-breaker starvation path it would have opened, and close the
mid-session supervisor-continuity gap that night-earlier forensics proved.

## Decisions recorded (operator, 2026-09-10 21:40 IST)

1. **Run lineage: 134427 canonical.** The 20:41 IST fresh run (151114,
   started from a VS Code terminal WITHOUT --resume while 134427 was
   stale-ongoing) was ended with an ``operator_termination`` event; 134427
   was resumed through the production task, preserving its span from the
   13:44:27Z start. 151114's 393 post-market cycles stay recorded but carry
   no phase-gate weight.
2. **Intake semantic: read-only status telemetry** (ADR-006 Amendment 4).
   Real-orders-via-/placeorder rejected for P5 (order interception changes
   the system under test; would have forced a span-resetting restart).
   Deferred follow-up: a real gateway-side decision-telemetry intake.
3. **Continuity hardening: 5-minute watchdog task** (``LOATS_P5_Watchdog``)
   running the existing hidden wrapper; the OS-level claim lock turns
   overlapping fires into refusals (rc=2), not double writes.
4. **PR now** for the two pending validated commits (be5047d, 9396384) --
   protection relax/restore per standing practice; this wave joins the
   same push.

## Findings addressed

1. **Routing failures shared the market-data breaker (P1, fixed).**
   ``place_analyzer_request`` counted on ``OPENALGO_CIRCUIT_BREAKER``
   (threshold 3 / 60 s). Under the read-only semantic, the first three
   routed decisions of any session are EXPECTED 404s -- which would have
   opened the breaker every market-data call shares: the Amendment 3
   cascade (10,332 position_book 404s -> breaker flap -> 52,804 cycle
   errors -> CMP starvation) reproducible through the routing route,
   burying the run's first decisional evidence. Root cause: the analyzer
   path never had its own isolation member.

2. **Mid-session supervisor death had no recovery path (operational,
   fixed).** The 134427 writer (PID 34076) died at ~20:35 IST with a live
   terminal teardown (host up, no WER crash event, no shutdown banner --
   the 0xC000013A class). The logon-only resume task cannot fire
   mid-session, so the span burned idle until an operator noticed. The
   supervisor must never run attached to an interactive terminal.

## What was implemented

- ``src/loats/utils/circuit_breaker.py``: new
  ``ANALYZER_CIRCUIT_BREAKER`` (5 consecutive failures / 120 s recovery --
  an error BUDGET: a routing 404 is expected telemetry under Am4, not a
  gateway outage).
- ``src/loats/openalgo.py``: ``place_analyzer_request`` routes through the
  dedicated breaker; the shared breaker never sees routing outcomes.
- ``src/loats/alerts.py``: ``get_circuit_breaker_status()`` exposes the
  ``analyzer`` member (state invisible to operators is isolation that
  didn't happen).
- ``tests/test_analyzer_breaker_isolation.py`` (new, RED-first): drives
  REAL routing (engine -> real client -> real breaker-wrapped method; only
  the ``_request`` HTTP seam patched) to the threshold and pins: dedicated
  breaker opens + rejects the next attempt, shared breaker closed with
  zero failures, market-data-shaped call passes while the analyzer breaker
  is OPEN, status-surface membership, posture pins.
- ``docs/ADR-006-analyzer-routing-p5.md``: Amendment 4 (decision +
  isolation + continuity record).
- Host ops (not repo files): 151114 ended with full operator_termination
  evidence; 134427 resumed via ``schtasks /run LOATS_P5_Resume``;
  ``LOATS_P5_Watchdog`` created (5-min trigger, same hidden VBS wrapper).

## Verification (Windows, loatsNEW venv, measured)

- RED: new suite failed at collection pre-fix
  (``ImportError: cannot import name 'ANALYZER_CIRCUIT_BREAKER'``).
- Seam lesson en route: a fake CLIENT class silently discards the
  breaker-wrapped production method (first GREEN attempt passed 3/5 with
  the breaker never exercised -- caught because the "open" assertion ran
  against a breaker no code had touched). Final harness patches only
  ``AsyncOpenAlgoClient._request``.
- GREEN: ``pytest tests/test_analyzer_breaker_isolation.py -q`` -> 4
  passed, rc=0.
- Full-tree bundle (exclusive): ``pytest tests/ --cov=src
  --cov-fail-under=80`` -> **1764 passed, 88.19%**, rc=0 (caches purged
  first per HC-12 discipline). Lockstep surfaces
  (test_repo_hygiene + test_todo25_verifier_gates): 120 passed at the
  final ceiling.
- Static gates on all touched files: ruff check / ruff format --check /
  isort --check-only / flake8 / mypy --strict / bandit, all rc=0.
- HC registry sweep: **27 PASS / 0 FAIL / 0 SKIP, REGISTRY HEALTHY**,
  rc=0. fr7 health check: **32 PASS / 0 FAIL / 0 SKIP** (451.8 s), rc=0.
- External verifiers on the amended tree: verify_f8h01_external **17/17**,
  verify_f8m02_m07 **19/19**, verify_f8h02 **7/7**, all rc=0.
- Gitleaks clean: worktree detect (20.30 MB, no leaks) + introduced-
  commits scan (origin/main..HEAD, 2 commits, no leaks), rc=0.
- pip-audit (production closure, 2.10.1): rc=0 with the ADR-0010 waiver;
  safety 3.8.1 ``check``: rc=0, 1 ignored -- reports at the canonical
  gitignored paths reports/security/pip-audit.json /
  reports/security/safety-report.json.
- Latency benchmark (exclusive window): **overall_status=PASS,
  cmp_validation 10/10, benchmark_validation 2/2**
  (reports/performance/performance_benchmark_20260911_003100.json).
- Run continuity (live): ``schtasks /run LOATS_P5_Resume`` -> writer
  claimed, ``restarts`` 0->1, events ``writer_claimed`` + second
  ``routing_enabled``, counters floored honestly, staleness warning
  cleared; span preserved (0.12d at resume vs 0.12d required span start).
- Watchdog live-fire evidence: task created 22:05 IST; overnight host
  event absorbed UNATTENDED -- 134427 shows ``restarts`` 2, fresh writer
  (claimed 23:48:26Z), 0 exceptions, span accruing from the 13:44 start.
- Gates, coverage, benchmarks: final results appended below on completion.

## Run lifecycle (operator-approved)

- 151114 ended 2026-09-10T16:33:57Z with ``operator_termination`` (reason:
  fresh-start error, superseded by canonical 134427 per ADR-006 Am3 s4).
- 134427 resumed 2026-09-10T16:34:53Z through the production task
  (restarts=1), again 2026-09-10T23:48:26Z after the overnight host event
  (restarts=2). The 14-day span is measured from ``started_at``
  2026-09-10T13:44:27Z throughout.
