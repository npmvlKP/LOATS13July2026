# F8-L-06 Closure — LOATS_SUPPRESS_NLTK_WARNING was a verified no-op

**Closed:** 2026-09-04 · **Priority:** P3 (accepted as "documented, acceptable"
in 01Sep2026-FR.md) · **Branch:** `fix/fr7-wave`

## Finding

F8-L-06 recorded a single benign pytest warning (newspaper4k: `UserWarning:
nltk is not installed. Some NLP features will be unavailable.`) and accepted
it with the suppression knob `LOATS_SUPPRESS_NLTK_WARNING` as the documented
remedy. Forensic re-check found the knob had **never worked**: with the knob
set to `1`, a fresh interpreter still prints the warning.

Evidence (Windows git-bash, loatsNEW venv, 2026-09-04):

```
$ python -c "import warnings; import loats.sentiment"
... newspaper\parsers.py:19: UserWarning: nltk is not installed. ...

$ LOATS_SUPPRESS_NLTK_WARNING=1 python -c "import warnings; import loats.sentiment"
... newspaper\parsers.py:19: UserWarning: nltk is not installed. ...   # unchanged
```

## Root cause

Four defects, one symptom:

1. **Order-of-imports no-op (primary).** In `src/loats/sentiment.py` the
   guard `if os.environ.get(...) == "1": warnings.filterwarnings(...)`
   sat *after* `from newspaper import Article`. newspaper4k emits the
   warning at *its own import time* (`newspaper/parsers.py`), so the
   filter was always installed one statement too late. Classic
   symptom-patch: the code looked right and was dead on arrival.
2. **Unreachable documented interface.** `.env.example` presented the knob
   as a `.env` entry, but pydantic-settings loads `.env` into the Settings
   model only — it never touches `os.environ` — and no `load_dotenv` exists
   anywhere in `src/`. The documented path could not reach the guard.
3. **Over-broad suppression (latent).** The guard used
   `filterwarnings("ignore", category=UserWarning)` with no message
   pattern — had it worked, opting in would have blanket-muted every
   UserWarning in the process, including unrelated diagnostics.
4. **Dead Settings field.** `Settings.loats_suppress_nltk_warning` had zero
   consumers; the comment claimed "runtime consistency" that did not exist.
   (The lazy-settings contract, HC-21, correctly forbids reading
   `settings.*` at import time — the field could never have backed the
   import-time guard.)

## Fix

1. `src/loats/sentiment.py` — guard moved **before** the newspaper import;
   suppression scoped to the exact message
   (`message=re.escape("nltk is not installed")`, `category=UserWarning`);
   rationale documented at the site.
2. `src/loats/config/settings.py` — dead `loats_suppress_nltk_warning`
   field removed (verified zero references outside sentiment.py's stale
   comment).
3. `.env.example` — stale active key `LOATS_SUPPRESS_NLTK_WARNING=0`
   removed; comment block rewritten: durable fix is installing the optional
   nltk dependency (`pip install 'newspaper4k[nlp]'` — cosmetic only, the
   fallback whitespace tokenizer is functionally equivalent), temporary fix
   is setting the variable
   in the **process environment** (POSIX `export` / PowerShell
   `$env:`), with the explicit note that a `.env` line cannot work.
4. `scripts/check_repo_hygiene.py` — tracked-file ratchet re-pinned
   425 → 426 in lockstep (+1 this closure record).

## Regression coverage (RED-proven, then GREEN)

`tests/test_sentiment.py::TestNltkWarningSuppression` — 4 tests, each
spawning a fresh interpreter (the warning fires once per process at import
time, so in-process assertions cannot observe the contract):

- knob=`1` → scoped `ignore` filter exists **and** the warning does not
  reach stderr (end-to-end outcome, not implementation detail);
- knob unset → no filter, warning visible on stderr;
- knob=`0` → no filter, warning visible (fail-open by design);
- the installed filter matches the real message text and no
  pattern-less `UserWarning` ignore exists (scoped, not blanket).

Probes match filters via `f[1].match(real_message)` — comparing the
pattern *string* is a trap because `re.escape` backslash-escapes the
spaces (`nltk\ is\ not\ installed`), which silently fails a
`.startswith("nltk is not installed")` check.

RED evidence: against the pre-fix code,
`test_knob_set_to_1_installs_scoped_ignore_filter` failed with
`SENTINEL-INACTIVE`; post-fix the class runs 4/4.

## Collateral root-cause fix (pre-existing, same gate surface)

`scripts/check_env_settings_sync.py` was failing at HEAD: three Settings
fields had no `.env.example` keys (`VIX_GATE_THRESHOLD`,
`SOURCE_BREAKER_FAILURE_THRESHOLD`, `SOURCE_BREAKER_TIMEOUT_SECONDS`).
Keys added mirroring the Settings defaults (15.0 / 3 / 60.0); sync now
reports 46 vars / 46 fields, PASS. HC-23 verifier unaffected (3/3).

## Validation (Windows, loatsNEW, 2026-09-04)

- `pytest tests/test_sentiment.py tests/test_sentiment_coverage.py` → 23 passed
- `pytest tests/` (full suite) → **1419 passed, 4 warnings** in ~190s:
  1× the historical nltk UserWarning (this runner process, knob unset —
  correct fail-open) + 3× pre-existing `coroutine never awaited`
  RuntimeWarnings in `tests/test_single_engine_consolidation.py`
  (AsyncMock into `scheduler.add_job`; untouched by this wave, logged as
  residual debt)
- Coverage gate (CI mirror): `pytest tests/ --cov=src --cov-branch
  --cov-fail-under=80` → 87.47%, floor met; per-module floors PASSED
- `check_env_settings_sync.py` → PASS 46/46 (was failing at HEAD)
- `verify_env_example_hc23.py` → PASS; `verify_f8h01_external.py` → 17/17;
  `verify_f8c02_external.py` → 12/12; `verify_todo27_external.py` → 41/41;
  `eval_f8l05.py` → 10/10
- `ruff check .` clean; `ruff format --check src/ tests/ scripts/` clean;
  `isort --check-only src/ tests/ scripts/` clean; `flake8 src tests scripts`
  clean; `mypy --strict src` clean; `bandit -r src/` exit 0;
  `pre_commit validate-config` exit 0; `gitleaks detect --no-git` exit 0;
  `pip_audit --skip-editable` → "No known vulnerabilities found";
  `check_repo_hygiene.py` PASS (416 tracked, ceiling 426)
