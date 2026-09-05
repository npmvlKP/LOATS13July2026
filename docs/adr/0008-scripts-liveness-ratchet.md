# ADR 0008: scripts/ Liveness Ratchet and Enforced Commit Format (F8-L-06-R2)

## Status
Accepted — 2026-09-05

## Context
The 2026-09 maintainability review flagged scripts/ as the fastest-eroding
maintainability surface. Measurement at HEAD `1c41c7c` (branch
`fix/fr7-wave`, clean tree, 429 tracked files):

* **49 of 90 tracked `scripts/*.py` were dead.** Reference census (git grep
  of each basename across CI, pre-commit, tests/, src/, pyproject.toml,
  living docs, then inside scripts/ for the dependency cascade) showed they
  were cited only by `docs/audit-history/` and `reports/ai-generated/` —
  the frozen archives that cite everything their wave ever touched. These
  are one-wave `verify_todoNN_*`/`fix_*`/`probe_*` relics whose checks were
  already superseded by the test suite (e.g. `verify_todo22_ruff_ignore.py`
  verified ruff per-file-ignores that no longer exist). Nothing failed
  while they rotted because nothing ran them — invisible rot by design.
* **7 orphaned report artifacts** sat in `reports/` (executable helpers
  `verification-external.{py,sh,ps1}`, `verify_f8h04_external.py`, and
  JSONs no live surface reads) — the exact root-reports clutter class the
  review called out; the tracked venv and root-report claims from the same
  review were already stale (fixed by F8-C-02/F8-M-05 waves).
* **5 dead `[tool.ruff.lint.per-file-ignores]` entries** pinned rules for
  files that no longer exist (`quick_health_check.py`, `setup_project.py`,
  `comprehensive_verify_todo26.py`, `verify_todo22_ruff_ignore.py`,
  `user_verify_deployment.py`) — lint config as fiction.
* **Status-essay commit subjects for 5 consecutive commits**
  (`Update: <evidence narrative>`), while CONTRIBUTING.md already mandated
  `<type>: <subject>`. Root cause: `scripts/commit_message_check.py` was
  configured in `.pre-commit-config.yaml` but **no git hook was installed**
  (`.git/hooks/` held only non-executable `commit-msg.{bat,ps1,txt}`
  leftovers), and `core.hooksPath=.git/hooks` made `pre-commit install`
  refuse to run ("Cowardly refusing...").

## Decision
1. **Delete the 48 dead scripts and 7 orphaned artifacts** (55 tracked
   files). Keep-decisions
   at the zero-external-reference boundary: `stress_rule7_concurrency.py`
   (live test wiring — `tests/test_rule7_concurrency.py` shells out to it),
   `collect_p1_phase_gate_evidence.py` (generator of
   the tracked P1 evidence of record), `eval_f8l05.py` (guard-wired in
   `check_repo_hygiene.py`), `probe_hc14_ops_limiter.py` (consumed by
   `verify_hc_registry.py`, cited by ADR-006), `utils.py` +
   `pip_audit_wrapper.py` (audit-narrative citations only — the rot class
   itself, kept deliberately until their waves document alternatives).
2. **Make orphaned scripts a machine-checkable failure**:
   `scripts/check_scripts_wiring.py` computes liveness to a fixpoint from
   live citation roots (CI, pre-commit, tests/, src/, pyproject, .flake8,
   README/RUNBOOK/CONTRIBUTING/DEPLOY, living docs, the two pinned P1
   evidence artifacts) through intra-scripts citations, and rejects
   src//tests back-references into scripts/ (grandfathering the documented
   `win32_root_junk` lockstep idiom). Dead cliques stay dead by
   construction — seeds only, never reverse closure. Wired into CI
   (`repo-hygiene` job), pre-commit (`scripts-wiring`), and the health
   check as HC-30 (delegating to the same script CI runs, so HC cannot
   drift from CI).
3. **Enforce the Conventional Commit first line** in
   `commit_message_check.py` (type in feat/fix/docs/style/refactor/perf/
   test/chore/build/ci, optional scope, optional `!`). Merge/revert
   subjects are exempt (git-generated). The 50-char subject guidance stays
   a documented convention, deliberately unenforced. Prohibited-phrase
   rule unchanged.
4. **Install the hooks on the dev host**: unset the redundant
   `core.hooksPath`, run `pre-commit install --hook-type commit-msg`,
   delete the non-executable legacy hook leftovers.
5. **Truth the config**: drop the 5 dead per-file-ignores; update the
   stale `<= 415` docstrings in `verify_f8c02_external.py` to the live
   429 lockstep value (behavior was already correct; comments lied).

## Consequences
* scripts/ shrinks 90 → 43 files, every one reachable from a live surface;
  the guard keeps it that way (a new script merged without wiring fails
  CI, pre-commit, and HC-30 simultaneously).
* Commit subjects must describe the change; wave evidence moves to
  reports/ and docs/audit-history/ where it belongs.
* New HC-30 extends the health-check registry; `verify_hc_registry.py`
  enumerates HC-01..HC-27 only and is unaffected (fixed catalogue, no
  unknown-id rejection).
* The ratchet ceiling stays 377 until the next wave re-pins all four
  surfaces in lockstep (net file count: 429 - 55 deletions + 3 additions:
  the guard, its regression net, this ADR).

## Evidence (all commands executed live on Windows, 2026-09-05)
* `python scripts/check_scripts_wiring.py` → `OK scripts wiring clean
  (43 scripts, all cited live)`, rc=0 after rc=1 on the pre-fix
  tree listing the held-back orphans — the RED/GREEN pair.
* `pytest tests/test_scripts_wiring.py tests/test_repo_hygiene.py
  tests/test_todo25_verifier_gates.py -q` → 78 passed (includes the
  commit-gate parametrization: conventional OK, status-essay rc=1,
  prohibited phrase rc=1, merge/revert exempt, `!` accepted).
* 2 initial test failures were test bugs, not guard bugs (lambda ignored
  the liveness filter; grandfather test used a dotted form the import
  regex never matched) — both fixed, suite green.
* Eval: the pre-wave commit gate scored 7/11 on an 11-case message
  matrix; the post-wave gate scores 11/11 (misses were exactly the
  status-essay class: `Update:` subjects, unprefixed subjects, `wip:`,
  empty messages).
* Regression caught and fixed by the full suite: the first deletion wave
  removed `scripts/stress_rule7_concurrency.py` (its only live citation
  is `tests/test_rule7_concurrency.py`, which shells out to it); the
  run failed RED, the script was restored, and the test passed GREEN.
  The wiring guard now also counts it live.
