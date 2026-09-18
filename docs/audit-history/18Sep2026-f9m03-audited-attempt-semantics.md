# F9-M-03 Audited-Attempt Semantics (ADR-006 Amendment 7) - Resolution Record

**Date:** 2026-09-18 (Asia/Calcutta)
**Wave:** F9-M-03 / TODO-8 closure — the last open code item of the
FR9 P2 track. Operator decision 2026-09-18: **option (a), audited-attempt
semantics** (~2 h) over option (b), building the gateway-side intake
endpoint (1–2 days).

## Root cause addressed

1. **Acceptance-semantic gap, not a routing gap (this wave's decision).**
   The engine has routed every TradeDecision with a real HTTP call since
   the F9-C-02 span (dedicated ``ANALYZER_CIRCUIT_BREAKER``, per-outcome
   counters, trade_decisions row + ROUTE audit row per attempt), and the
   gateway 404s each attempt by design under the Amendment 4 read-only
   semantic. What was missing was GRADER acceptance: P5 "route ALL"
   grading could not formally close while the accepted evidence semantic
   lived only in ADR prose. Amendment 7 resolves this: the routed
   ATTEMPT — one real HTTP call resolving honestly as success, disabled,
   or error — is the P5 decisional evidence.
2. **Legacy-run-log shape would fail the new gate silently (found while
   building, fixed same wave).** The accruing pre-semantic span's logs
   carry outcome counters WITHOUT ``routed_decisions``. A naive
   ``routed_decisions == 0`` attempt-gate would have hard-FAILed that
   legacy evidence stream the moment the semantic activated. The gate
   therefore keys on the KEY BEING PRESENT (post-semantic log) — mixed
   semantic eras (outcomes recorded, zero attempts) FAIL/INCOMPLETE
   explicitly; legacy logs grade exactly as before.
3. **Coverage-lock guard was not worktree-safe (found by this wave's
   full-suite run in the linked worktree, fixed same wave).** First
   full-suite run: ``tests/test_coverage_lock_guard.py::
   TestCovLockKillSwitch::test_disabled_env_admits_cov_run_despite_
   held_lock`` died with ``FileExistsError: ... f9m03\\.git`` — in a
   linked worktree ``.git`` is a pointer FILE, and the guard's
   ``mkdir(parents=True, exist_ok=True)`` cannot create it. A/B-proven
   pre-existing (identical failure on a pristine 7014186 worktree) —
   the same worktree-shape hazard class the 2026-09-11 wave fixed in
   the hygiene net. Fix: ``tests/conftest.py::_cov_lock_path`` resolves
   the pointer file directly (no subprocess) to the real admin dir;
   plain layout unchanged; +5 pins in ``TestCovLockWorktreeShape``
   (guard suite 14->19). Both sub-process guard tests now pass
   end-to-end in the worktree.
4. **Ratchet history-structure misunderstanding (caught in self-review).**
   First insertion attempt edited the WRONG history list and renamed a
   historical entry (408 -> 437). Repaired before commit: history
   entries are append-only logs of their own wave's ceiling; the only
   editable pin is ``TRACKED_FILE_CEILING`` (437 -> 439) and the new
   dotted entry 439.
5. **Session-artifact interplay with the hermeticity probe (diagnosed,
   remediated; probe unchanged).** This wave's external-verifier gate
   run imports the loats db singleton OUTSIDE pytest (no conftest env
   pinning), so its default ``data/`` paths materialized a PARTIAL data
   tree (``loats.db`` with content, 0-byte ``audit.log``) inside the
   worktree. The F9-C-02 hermeticity probe skips only when BOTH files
   are missing, so the partial tree sent it down the live-system branch
   where ``st_size > 0`` failed deterministically. Both files were
   created at the minute of the verifier run (ctime-proven) and are
   git-ignored; the artifact was removed (fresh-clone shape restored,
   probe skips by design) and the main checkout's live data was never
   touched. Lesson recorded: external verifier runs belong in a
   disposable checkout, or ``data/`` must be pre-created empty-free.

## Changes

- ``docs/ADR-006-analyzer-routing-p5.md``: Amendment 7 appended
  (newest-first by date, above the 2026-09-12 Amendment 6):
  audited-attempt semantic, the machine-readable single source, grader
  upgrades, the not-a-fabrication-class clause, and the config-only
  option-(b) activation path (Amendment 5 preserved).
- ``src/loats/trade_decision.py``: new ``routed_decisions`` counter,
  incremented exactly once per ENABLED route BEFORE any outcome exists
  (disabled path never reaches it); new class attribute
  ``analyzer_intake_semantic`` — the accepted semantic as data
  (``{"intake_semantic": "audited_attempt",
  "audited_attempt_outcomes": ["success", "disabled", "error"],
  "adr": "ADR-006 Amendment 7", "decision": "F9-M-03 option (a)"}``);
  ``get_routing_stats`` docstring updated. Runtime behavior otherwise
  untouched: no payload, breaker, or audit-row change.
- ``scripts/verify_p5_forward_test.py``: ``_analyzer_intake_semantic()``
  (zero hard ``loats`` imports; returns None when the package is
  unavailable -> logs grade unchanged); the decisional gate grades
  routed ATTEMPTS: post-semantic log with zero attempts while outcomes
  exist -> ENDED run FAILs, ONGOING run stays INCOMPLETE with the
  reason surfaced; legacy logs (no key) grade unchanged; the attempt
  total never feeds the exception or divergence criteria.
- ``tests/test_f9m03_audited_attempt.py`` (new): 15 pins across the
  semantic source, per-path attempt counting (success / designed-404
  error / disabled / mixed-path invariant attempts >= outcomes), the
  grader branches (attempt-PASS / attempts-alone-PASS with zero cycles /
  ended-FAIL / ongoing-INCOMPLETE / legacy-unchanged / divergence
  non-whitewash), and supervisor flow (baseline capture + live delta
  fold with NO supervisor change).
- ``tests/test_analyzer_intake_contract.py``: Contract 7 — the Am.7
  semantic-source exact-dict pin.
- ``tests/test_p5_forward_test.py``: exact-dict counter-pin maintenance
  (``TestRoutingCounters`` gains ``routed_decisions``) — the documented
  convention from the F9-C-02 divergence-flag addition; found by the
  full-suite run, fixed before commit.
- ``tests/test_coverage_lock_guard.py``: Contract 5 — worktree-safe
  lock placement (+5 pins; guard suite 14->19); concomitant
  root-cause fix in ``tests/conftest.py::_cov_lock_path`` (gitdir
  pointer-file resolution, no subprocess; A/B-proven pre-existing on
  pristine 7014186).
- ``scripts/ratchet_baseline.py``: ``TRACKED_FILE_CEILING`` 437 -> 439
  (+2: this record + the new test net), dotted history entry 439.

## RED/GREEN evidence

- RED (semantic source, pre-implementation on the worktree's own HEAD):
  ``tests/test_analyzer_intake_contract.py -k SemanticSource`` and
  ``tests/test_f9m03_audited_attempt.py::TestSemanticSource`` fail with
  ``AttributeError: type object 'TradeDecisionEngine' has no attribute
  'analyzer_intake_semantic'``.
- GREEN: full new net 15/15 after implementation; extended contract net
  8/8; coverage-lock guard suite 19/19 including the previously-failing
  kill-switch test (worktree-safe now); full suite green (see PR CI for
  the authoritative run).
- Isolation: developed in worktree ``../LOATS13July2026-f9m03`` with its
  OWN venv (editable install of the worktree); the main checkout's code
  is untouched and its supervised span keeps accruing on the pre-semantic
  counters, which the grader grades unchanged (legacy clause, tested).

## Impact

- F9-M-03 (TODO-8) CLOSED: P5 "route ALL" grading no longer blocks on
  the deferred gateway intake. The last open code item of the FR9 P2
  track is resolved; remaining risk items are P0 (passive counter,
  watchdog-guarded), P1 (F9-H-02, post-30Sep, grade-gated), P3 (venv
  rebuild 01 Oct).
- Option (b) remains config-activatable without deploy or restart
  (``ANALYZER_INTAKE_PATH``, Amendment 5); when flipped, genuine
  successes accrue under the same counters and the audited-attempt
  total remains a strict superset of them.
