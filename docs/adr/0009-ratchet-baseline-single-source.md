# ADR 0009: Single imported source for the tracked-file ratchet ceiling (F8-L-07)

## Status
Accepted — 2026-09-05

## Context
The 2026-09 maintainability review ("next wave must re-pin all 4
surfaces in lockstep") surfaced the structural weakness behind the
recurring ratchet re-pins: the tracked-file ceiling existed as the same
hand-pinned integer in four gate scripts:

* `scripts/check_repo_hygiene.py` (`TRACKED_FILE_CEILING` — CI
  `repo-hygiene`, pre-commit `repo-hygiene`, HC-26 delegation)
* `scripts/verify_f8c02_external.py` (check 1 and the check-12 grep)
* `scripts/verify_todo21_external.py` (`baseline_count`)
* `scripts/verify_todo21_root_cleanup.py` (`baseline_count`)

Lockstep was procedural: every wave that added or removed tracked files
had to remember all four sites plus the surrounding comment narratives
that restated the numbers. This already failed once — the 416-vs-426
split left two committed gates failing on a clean tree — and
`verify_f8c02_external.py` drifted again in prose (docstrings claiming
429 while the code pinned 377). The wave immediately before this one
(F8-L-06-R2, ADR-0008) repeated the four-site hand-sync verbatim,
reproducing the very defect class it documented.

Also corrected here: ADR-0008's keep-decision list named `utils.py` +
`pip_audit_wrapper.py` as deliberately kept on audit-narrative
citations; commit `e24579d` in fact deleted both (55-file deletion,
net -52). The review's "kept on audit-narrative citations only" and
"69 tracked scripts" describe older trees (measured: 90 tracked
`scripts/*.py` at the ADR-0008 baseline commit `1c41c7c`; the "69"
figure appears in the 01Sep2026 audit record for the pre-venv-sweep
tree). The tracked `scripts/` count at this wave is 43.

Two further holes surfaced during adversarial verification of this
wave, both closed:

* `verify_todo21_external.py` resolved its project root from
  `Path.cwd()`, so a bare invocation from any other directory failed
  confusingly; it now defaults to the repository the script lives in
  (the `verify_f8c02_external.py` convention), pinned by
  `tests/test_todo25_verifier_gates.py::TestVerifierCwdIndependence`.
* The lockstep regression test accepted a verifier that pinned the
  baseline BOTH ways (an import line plus a stale literal), letting the
  stale literal hide behind the imported branch; it now requires each
  surface to pin exactly once.

## Decision
1. `scripts/ratchet_baseline.py` becomes the single source of truth for
   `TRACKED_FILE_CEILING` (stdlib-only, side-effect-free, importable
   from any context: CI, pre-commit, health-check subprocess, importlib
   spec-load).
2. All four ratchet surfaces import the constant instead of pinning a
   literal (`from ratchet_baseline import TRACKED_FILE_CEILING`,
   sys.path-seeded as `check_repo_hygiene.py` already does for
   `win32_root_junk` — scripts/ is not a package). The guard re-exports
   the name unchanged, so `guard.TRACKED_FILE_CEILING` consumers are
   unaffected.
3. `verify_f8c02_external.py` check 12 asserts the import +
   `baseline_count = TRACKED_FILE_CEILING` in both TODO-21 verifiers
   instead of a magic number, and its stale 429 prose now names the
   constant.
4. Regression nets are extended: `tests/test_repo_hygiene.py::
   TestRatchetSingleSource` asserts runtime agreement
   (`canonical.TRACKED_FILE_CEILING == guard.TRACKED_FILE_CEILING`)
   and that the guard carries no local literal;
   `tests/test_todo25_verifier_gates.py::TestRatchetLockstep` loads
   the canonical module, the guard, and the F8-C-02 verifier as live
   modules, and resolves the TODO-21 pins from their source text with
   end-of-line-anchored patterns (comment lines and arithmetic
   suffixes such as `TRACKED_FILE_CEILING + 10` cannot satisfy it) —
   the lockstep check survives refactors because it no longer greps
   the hygiene guard's source for a literal.
5. `verify_f8c02_external.py` docstrings/comments that restated the
   ceiling as 429 are corrected (code had pinned 377 since F8-L-06-R2;
   only prose drifted).
6. ADR-0008 is amended: its keep-list inaccuracy is annotated in place
   and its "re-pin all four surfaces in lockstep" consequence is marked
   superseded by this ADR.

## Consequences
* The next tracked-file-count change edits ONE number and appends one
  history line in `scripts/ratchet_baseline.py`; forgetting a surface
  now fails three independent nets (unit lockstep tests, f8c02 check
  12, runtime agreement) instead of shipping silent drift.
* Comment narratives in the three verifiers shrink to one-line
  pointers; the authoritative pin history (369 -> 415 -> 416 -> 425 ->
  426 -> 429 -> 377 -> 379) lives beside the constant.
* The hygiene guard gains a scripts/-internal import at module load; it
  already seeds sys.path for `win32_root_junk`, so no execution context
  changes.
* Ceiling re-pinned 377 -> 379 in the same commit that adds the module
  and this ADR (+2 tracked files), per the ratchet protocol this ADR
  replaces.
* Known accepted limitation (documented, not fixed): the ratchet still
  permits silent LOOSENING — raising `TRACKED_FILE_CEILING` while the
  tree stays small passes every net, since no test pins the ceiling to
  the measured count. The sane-band test (350..510) bounds abuse. A
  `ceiling == measured` pin would break legitimate wave commits (the
  re-pin must land in the same commit as the file deltas), so tightening
  this stays a deliberate trade-off, revisitable if a wave pads the
  ceiling.
* `verify_f8c02_external.py` check 12 matches import statements
  textually; a future parenthesized or aliased import form would fail
  the check loudly (safe direction), and the message names the expected
  form.
