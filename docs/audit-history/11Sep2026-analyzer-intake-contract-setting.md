# Analyzer Intake-Contract Setting (Am5) - Wave Record

**Date:** 2026-09-11 (Asia/Calcutta)
**Wave:** P5 follow-up prep (day 1 of the 14-day span): remove the
client-side code-change dependency from the ADR-006 Amendment 4 deferred
intake so the gateway-side decision-telemetry endpoint, once it ships,
activates via configuration alone -- no deploy, no restart, span
preserved.

## Root cause addressed

1. **Hard-coded analyzer intake literal** (fixed this wave):
   ``AsyncOpenAlgoClient.place_analyzer_request`` hard-coded the intake
   endpoint literal ``"analyze"``. ADR-006 Amendment 4 decided the
   read-only intake semantic (every routed decision resolves as an honest
   HTTP-404 ``error`` outcome) and deferred the real gateway-side
   decision-telemetry intake as a P5 follow-up. The deferral's activation
   cost was therefore a source edit + deploy + supervised-run restart --
   contradicting the recorded intent of replacing the 404-error class
   "without touching the run."
2. **Worktree-unsafe git-dir path in the hygiene net** (pre-existing,
   found by this wave's isolated-development protocol, fixed same wave):
   ``tests/test_repo_hygiene.py::TestFixerHooksSpareFrozenEvidence::
   test_excludes_stripped_mutant_proves_the_mechanism`` wrote its mutant
   config to ``REPO_ROOT/.git/...``. In a linked worktree ``.git`` is a
   file (a gitdir pointer), so the write raised ``FileNotFoundError`` and
   the full suite ran 1767-passed/1-failed in this environment. A/B
   proven pre-existing: the pristine 7b03e83 worktree fails identically.
   Fix: resolve the real admin dir via ``git rev-parse
   --absolute-git-dir`` (returns ``REPO_ROOT/.git`` in the main checkout,
   ``<main>/.git/worktrees/<name>`` in a worktree -- a real directory on
   the repo drive, invisible to git status, never staged, in both
   shapes). All 104 hygiene tests pass post-fix.

## Changes

- ``src/loats/config/settings.py``: new ``analyzer_intake_path`` field
  (default ``"analyze"``) documenting the read-only semantic and the
  config-only activation path.
- ``src/loats/openalgo.py``: ``place_analyzer_request`` resolves the path
  per call via ``get_settings()``; payload and breaker wiring untouched
  (the Amendment 4 ``ANALYZER_CIRCUIT_BREAKER`` isolation is preserved).
- ``tests/test_analyzer_intake_contract.py`` (new): RED-first net -- 7
  cases pinning default preservation, operator settability, singleton
  default, per-call resolution without reconstruction, endpoint flow
  (method/path/json payload), ``to_analyzer_payload`` immutability, and
  the single-source ceiling.
- ``tests/test_repo_hygiene.py``: worktree-safe git-dir resolution for
  the pre-commit mutant sweep (fix #2 above; no behavior change in the
  main checkout, ``rev-parse --absolute-git-dir`` returns the same dir).
- ``scripts/ratchet_baseline.py``: ceiling re-pinned 405 -> 407 (+2
  tracked files: this record + the test net), history annotated.
- ``docs/ADR-006-analyzer-routing-p5.md``: Amendment 5 appended
  (newest-first, per the file's convention).

## Evidence

- RED (pre-implementation, worktree's own code): 4 failed / 3 passed --
  failures exactly ``'Settings' object has no attribute
  'analyzer_intake_path'`` (x3) and the literal-not-sourced pin; the
  default-flow case passed against the unmodified tree (it pins existing
  behavior by design).
- GREEN (post-implementation): 7/7 passed (0.14 s).
- Environment note: the shared loatsNEW venv's editable install resolves
  ``loats`` to the main checkout via a .pth meta-path finder regardless
  of ``PYTHONPATH``; this wave was therefore developed and validated in
  an isolated worktree with its own venv (editable install of the
  worktree), keeping main @ 7b03e83 untouched for the live supervised
  run (134427).
