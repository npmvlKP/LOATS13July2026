# Verifier-Gate Integrity Wave (2026-09-13)

**Wave ID:** verifier-gate-integrity-20260913
**Base:** main @ `3bd32f6` (post PR #30)
**Scope:** two born-red external verifier gates repaired to outcome-scoped
grading; regression nets added; zero production (`src/`) changes.

## Why

The 2026-09-13 session ran the full external-verifier sweep on a clean
tree at HEAD. Two verifiers exited 1. Investigation showed both were
NOT detecting product defects -- they were failing on correct code,
each for a different structural reason:

1. `verify_coverage_full.py` was born-red on every compliant
   environment, and could only ever "pass" by grading stale artifacts.
2. `verify_todo24_external.py` pinned implementation idioms that the
   canonical gate legitimately outgrew (the F8-M-03 "idioms not
   outcomes" erosion class, in a verifier built to police that gate).

A verifier that fails correct code is as broken as one that passes
broken code. Both were repaired at the contract level; neither gate
was weakened.

## Root causes and fixes

### verify_coverage_full.py (embedded pytest + coverage grading)

| # | Defect | Root cause | Fix |
| --- | --- | --- | --- |
| 1 | Embedded pytest died rc=4 before running any test | `--timeout=10` requires the `pytest-timeout` plugin, declared nowhere (pyproject/requirements/CI); argparse usage error on every run. Also caught during repair: `--junitxml` was removed in pytest 9 (installed 9.1.1) -- the regression net flagged the replacement flag immediately | Flag removed; the outer `subprocess.run(timeout=900)` is the real bound; net `test_embedded_pytest_uses_no_undeclared_plugin_flags` validates every embedded flag against the installed pytest's `--help` vocabulary |
| 2 | `[PASS] coverage.json generated` printed on a STALE report | The stale root `coverage.json` (written by an earlier unrelated run) satisfied the existence gate; timeline proved acceptance of pre-run evidence (run died ~1s, file predated it) | Path pinned `--cov-report=json:coverage.json`; stale file unlinked BEFORE the run; crash now fails the existence gate closed; net pins unlink-before-run ordering |
| 3 | Grading heuristic `"passed" in line` | Also accepts a failing summary (`2 failed, 500 passed`), and graded nothing when the run produced no summary at all | Verdict = exit code 0 AND parsed `>0 passed` AND `0 failed` (summary regexes); net rejects the substring heuristic's return |
| 4 | Frozen 5-file subset scope | Subset totals cannot satisfy the repo-wide `fail_under = 80` (`[tool.coverage.report]` grades the total across measured modules; the subset measured ~35%): the gate was DOUBLY born-red, which is why stale artifacts were being graded. The docstring still claimed "full suite" from the 23Aug-era 219-test tree | Scope restored to CI parity: full `tests/`, `--cov=src --cov-branch --cov-fail-under=80` (the exact `pytest-coverage` job command). Per-module floors DELEGATED to the canonical `scripts/check_per_module_coverage.py` -- one floor map in the repo, not two that drift |

### verify_todo24_external.py (stale pins on the canonical floor gate)

| # | Stale pin | Live symptom | Fix |
| --- | --- | --- | --- |
| 1 | Success `sys.exit(0)` pinned to LINE 177 of `check_per_module_coverage.py` | `[FAIL] Exit Semantics Source` (success exit now at line 250 after the stale-artifact + grading-loop waves) | Positional contract: exactly one `exit(0)`, >=4 `exit(1)`, and the FINAL exit statement must be the success exit -- the fallthrough-safety property itself |
| 2 | Exact historical unit-test name list (`test_exit_0_all_modules_pass_threshold` et al.) | `[FAIL] Unit Tests Exist` while `Unit Tests Pass` passed -- the suite was renamed by the behavioral wave | AST-based discovery graded by behavioral classes: success (`_passes`), >=3 failure paths (`_fails`), stale-artifact rejection, explicit artifact path |
| 3 | Docstring prose keywords `"80%"` / `"threshold"` | `[FAIL] Documentation` on a docstring that states the real contract | Contract keywords: `coverage`, `floor map`, `fallback` (the anti-narrowing property F8-H-04 pins) |
| 4 | `uv run pytest` environment branch | Wrong-environment resolution when `uv` exists without the project venv; also graded stdout by substring | Explicit repo-venv interpreter (`loatsNEW` / `.venv` / `sys.executable`), quiet flags, no cache writes; rc + parsed-count grading |

## Regression nets

`tests/test_todo25_verifier_gates.py` extended (+12 tests, sections 8-9):
flag-vocabulary pin (RED-proven live: it rejected `--junitxml` in this
wave's own first fix), fresh-evidence ordering, rc+count grading, absence
of the substring heuristic, line-number-pin ban, AST-based discovery,
contract-not-prose documentation pin, venv-explicit runner, and an
end-to-end green run of the repaired TODO-24 verifier against the live
gate.

## Verification state (measured, clean tree, repo venv)

- `python scripts/verify_coverage_full.py` -> rc=0, 9 PASS / 0 FAIL
  (full suite fresh; aggregate 88.9%; all floor-mapped modules green
  via `check_per_module_coverage.py`)
- `python scripts/verify_todo24_external.py` -> rc=0, 6/6 checks
- `pytest tests/test_todo25_verifier_gates.py` -> 29 passed (includes
  the RED-proven flag-vocabulary net)
- Static gates on changed files: ruff check / ruff format / isort /
  flake8 all rc=0
- Verifier sweep at base `3bd32f6`: 19 rc=0 (fr7_health_check 32/0/0,
  f8c01 7/7, f8c02 12/12, f8h01 17/17, f8h02 7/7, carried-set,
  todo21 x2, todo25 x2, todo27 x2, todo8, hc_all, hc_registry,
  probes x2), plus the two repaired here and `verify_p5_forward_test.py`
  rc=1 which is the EXPECTED honest verdict (run 150243 in flight,
  routing default-OFF pending operator enablement; window ~26Sep)

## Behaviour contract

- No production code changed; no gate thresholds changed; the only
  observable difference is that two verifier gates now tell the truth
  (green on a correct tree, red on a broken one).
- `verify_coverage_full.py` now takes ~4-5 minutes (full suite inside)
  instead of ~25 seconds (a dead 1-second run plus stale-artifact
  grading). The honest cost of real evidence.
- `coverage.json` at the repo root remains gitignored and is only ever
  graded when produced by the verifier's own run.
