# Coverage-Writer Mutual-Exclusion Wave (2026-09-13)

**Wave ID:** coverage-lock-guard-20260913
**Base:** main @ `49d8822` (post PR #31)
**Scope:** one production-adjacent test-infra fix in `tests/conftest.py`;
no `src/` changes; no gate thresholds changed.

## Why (the incident)

A manual `pytest --cov` run and `scripts/verify_coverage_full.py`
(then PID 33876) ran concurrently at ~12:33–12:41 IST. Both are pytest
processes writing coverage data in the repo root: each writes its own
parallel data file (`.coverage.<host>.<pid>.<rand>`), and each run's
combine step sweeps every sibling file. The manual run's combine swept
PID 33876's still-open data file and died on Windows mandatory-file
locking:

```
PermissionError: [WinError 32] The process cannot access the file
because it is being used by another process:
'.coverage.npmvl-KP-Boogey-Budigee.pid33876.XkIGfFVx'
```

 pytest surfaced this as an INTERNALERROR **after** `1815 passed` --
the run's verdict was lost. Second-order damage: the verifier's own
green completion overwrote `.pytest_cache/v/cache/lastfailed`, so the
losing run's single real test failure became permanently
unidentifiable (its identity, not its existence: the manual run later
re-ran solo at 1816 passed / 0 failed, and the wave's full-suite runs
are green, so no latent product defect existed behind it).

## Root cause

Not a coverage bug: pytest-cov's parallel-data combine is documented to
consume every sibling `.coverage.*` file. The defect is the absence of
mutual exclusion between concurrent coverage writers in this repo. The
writer class was enumerated: manual `pytest --cov` runs, CI's
pytest-coverage job, the pre-push pytest hook, and three verifiers with
embedded full-suite coverage runs (`verify_coverage_full.py`,
`fr7_health_check.py` HC-12, `verify_hc_all.py` self-measure). All of
them are **pytest processes**, so `tests/conftest.py` is the single
choke point for the entire class.

## Fix

`tests/conftest.py` grew a coverage mutual-exclusion guard wired in
`pytest_configure` (session scope, before any test runs):

- Any argv token starting `--cov` requests coverage (fail-safe
  detection: over-refusal is safe, under-refusal is not).
- A requesting run takes an exclusive cross-process lock
  (`.git/coverage_gate.lock`, msvcrt `LK_NBLCK` on Windows, fcntl
  `LOCK_EX` elsewhere) held for the interpreter lifetime via a
  module-global handle; the OS releases it on any exit path.
- A second concurrent writer is refused fail-closed **before any test
  runs** via `pytest.exit(..., returncode=4)` with a banner naming the
  collision mode and the kill switch. (`sys.exit` from a hook is
  swallowed and re-raised as an INTERNALERROR rc=3 -- caught live
  during RED/GREEN.)
- Non-coverage pytest runs are never gated; the kill switch
  `LOATS_COV_LOCK_DISABLED=1` bypasses the guard.

The lock file lives in `.git/` (invisible to status; the tracked-file
ceiling stays untouched by it).

## Regression net

`tests/test_coverage_lock_guard.py`: 14 tests, 13 born RED (live RED
run: 13 failed / 1 passed), now green in BOTH parent modes:

- plain parent: 14 passed
- `--cov` parent: 13 passed + 1 skip (the cov-parent-admission test
  documents its own skip; the kill-switch, refusal, and guard nets
  hold identically -- a full-suite cov run caught this test's own
  parent-mode assumption, which is exactly the class it polices)

End-to-end legs drive REAL subprocess pytest runs against the REAL
repo lock: cov run refused rc=4 while the gate is held (no tests
executed), cov run admitted when free, kill-switch child admitted
despite the held gate, plain runs never gated.

## Verification state (measured, repo venv, clean tree)

- Full suite with coverage through the guard:
  `pytest tests/ --cov=src --cov-branch --cov-fail-under=80` ->
  **1829 passed, 1 skipped, rc=0, total coverage 88.85%**, 7m02s
- Guard net both modes (above); static gates on the three-file delta:
  ruff check / ruff format / isort / flake8 all rc=0; mypy
  `src/ --strict` clean (38 files); bandit `src/` rc=0; gitleaks
  (tests+scripts tree scan, covers the uncommitted delta) no leaks
  rc=0; pip-audit `--ignore-vuln PYSEC-2026-3740` rc=0 (1 ignored =
  the ADR-0010-waived nltk advisory)
- Lockstep/hygiene/tree-reading nets: test_repo_hygiene +
  test_todo25_verifier_gates + test_scripts_wiring +
  test_coverage_floor_map -> 172 passed (ceiling re-pin protocol
  exercised: per-commit re-pin, see below)

## Behaviour contract

- No observable change for any single-writer workflow, CI, or the
  pre-push chain. The only observable difference: a second concurrent
  coverage writer is refused rc=4 with an explanatory banner instead
  of dying as an INTERNALERROR after minutes of green tests.
- Verifiers that embed coverage runs now fail closed at their own
  gate when the repo is busy (rc=4 embedded -> verifier FAIL), instead
  of crashing mid-run or corrupting each other's evidence.

## Ceiling protocol

Per-commit re-pin per the F8-L-07 single-source protocol: 412 -> 413
(test net) in the code commit, 413 -> 414 (audit record) in the
record commit; the ratchet history block carries both bumps.
