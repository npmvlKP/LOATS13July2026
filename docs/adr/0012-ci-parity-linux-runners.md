# ADR 0012: CI Parity with Linux Hosted Runners

## Status

Accepted — 2026-09-06

## Context

The first `workflow_dispatch` proof run of `fix/fr7-wave` (run
34016972202, 2026-09-06) executed the repaired mypy and pip-audit jobs
on GitHub-hosted runners. pip-audit passed; mypy, ruff-lint,
ruff-repo-scope, and pytest-coverage failed with **26 test failures +
coverage 0%** on a tree where every local gate was green (mypy clean,
87.49% coverage, 1515 tests passing on the Windows dev host).

Root-cause analysis of the CI logs (job logs preserved in the run
artifacts) found every failure in one of two classes:

1. **Install-parity class (dominant).** CI installed the package
   non-editable (`pip install ".[dev]"`), while the dev venv is
   editable. Consequences, all latent until the first true fresh-clone
   execution:
   - `pytest --cov=src` measured site-packages files that are never
     executed by the suite → coverage **0%**, tripping
     `--cov-fail-under=80`.
   - `src/loats/rss_validation.py` resolves `REPO_ROOT` via
     `Path(__file__).resolve().parents[2]` — the source-checkout
     layout. Under a non-editable install this anchor resolves into
     site-packages, where `tests/fixtures/rss/recorded-sources.json`
     does not exist → `RssManifestError` on 8 StartupGate /
     LiveRepositoryContract failures.
   - `verify_todo25_final.py` checked imports of `ta` and `vollib`,
     both deliberately dropped (ADR-0003, ADR-0004), imported nowhere
     in `src/` — ghost-dependency checks that fail only where the
     extras install correctly does not provide them.

2. **Environment-revealing class.** Code and tests carrying host
   assumptions that a fresh Linux 3.12 runner exposes:
   - `main.py` POSIX branch built the shutdown callback with a lambda
     whose parameter type mypy 2.3.1 cannot infer under unix event-loop
     stubs (`Cannot infer type of lambda`, `--platform linux`
     reproduces locally). The same lambda also bound a plain `int`
     where `_handle_shutdown_signal(sig: signal.Signals)` requires a
     `Signals` enum — a latent runtime bug on any POSIX deployment.
     Fixed with `_posix_signal_entry`, a bound method passed with the
     signal as `add_signal_handler` argument (no lambda at all).
   - 70 files carry shebangs but 100644 modes. EXE001 only fires where
     the exec bit exists (POSIX); NTFS cannot express it, so local ruff
     never saw it. Fixed by recording mode 100755 in the index.
   - `win32_root_junk.is_hostile_root_name` folded case only via
     `os.path.normcase` (identity on POSIX): committed names like
     `NUL.txt` would have escaped the class-wide scan on Linux. Fixed
     by casefolding in addition to normcase.
   - Logging tests mocked `Path.mkdir` away — simulating "no logs/
     directory" — yet required the `RotatingFileHandler` to open
     `logs/loats.log` successfully: contradictory on a fresh checkout
     (`Unable to configure handler 'file'`). Fixed hermetically: run
     production-mode tests in a tmp cwd and assert the REAL directory
     creation and handler construction.
   - `test_coverage_floor_map.py` read the gitignored
     `coverage_floor_map.json` from the repo root — a file that is a
     TODO-21 junk pattern and cannot exist in a fresh clone. The
     enforcement single source of truth is `FR_FLOOR_MAP` in
     `scripts/check_per_module_coverage.py`; the guard now pins that
     map (and the script's fail-closed fallback) as double entry.
   - `verify_todo21_root_cleanup.py` CHECK 2 failed a clean checkout
     because `reports/archived-audit/` (empty, untrackable) did not
     exist locally; the actual invariant — nothing stale still tracked
     — was already checked. Demoted to informational.
   - `verify_todo25_final.py` Stage 1 required the dev workstation's
     dedicated `loatsNEW` venv to exist and be in use. Adaptive now:
     dedicated venv required where it exists; on CI, the ephemeral
     hosted runtime is sanctioned.

## Decision

1. **CI installs EDITABLE** (`pip install -e ".[dev]"`) in the mypy and
   pytest-coverage jobs. This is the load-bearing contract for
   `--cov=src` measurement and for `parents[2]` fixture anchoring; a
   new `TestWorkflowFlagCurrency` guard pins it so it cannot silently
   revert.
2. **No `python_version` pin regression**: the `pyproject.toml` mypy
   config already carries `python_version = "3.12"`; the platform is
   intentionally left host-native, and platform-sensitive code paths
   are written stub-robust (typed bound method, no inference-dependent
   lambda).
3. **Exec bits** for every shebang file are recorded in the index
   (mode 100755), making EXE001 satisfied on every checkout surface.
4. **POSIX detection folds case** (normcase + casefold) so
   Windows-hostile names are caught class-wide on any host.
5. **Fresh-checkout hermeticity** for logging and floor-map tests; the
   untracked `coverage_floor_map.json` artifact was removed from the
   dev host so local and CI behavior are identical (the fallback map
   is the tested behavior).
6. **Verifiers are environment-adaptive, not environment-blind**:
   host-specific invariants (loatsNEW venv, archive directory with
   real archived content) are enforced only where their preconditions
   exist; CI's ephemeral runtime is sanctioned explicitly.

## Consequences

- The 383 tracked-file ceiling is re-pinned (+1, ADR-0009 protocol)
  for this decision record; headroom is 0 at head.
- The removed local `coverage_floor_map.json` changes nothing: it was
  gitignored, and the script's fallback map equals the enforced map by
  construction (and by test).
- Every fix is regression-netted: editable-install guard,
  floor-map double-entry test, flag-currency class unchanged.
- The next wave that adds a tracked file MUST first re-pin (re-measure
  and justify) — the same discipline as ADR-0009.
- WSL Ubuntu is available on the dev host for pre-push Linux parity
  checks (venv + suite) without burning CI cycles.
