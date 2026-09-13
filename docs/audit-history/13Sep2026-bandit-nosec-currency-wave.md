# Bandit `# nosec` Annotation Hygiene Wave (2026-09-13)

**Wave ID:** bandit-nosec-currency-20260913
**Base:** main @ `2ef3e39` (post PR #32)
**Scope:** four production-adjacent suppression-token removals in
`src/loats/database.py` (pattern replaced by `contextlib.suppress`), one
new 3-test currency net, governance records, ceiling re-pin. No behavior
change: all four sites are best-effort `conn.rollback()` fallbacks inside
outer handlers that log; every external contract (fail-closed raises,
log lines, return values) is byte-identical.

## Why (the incident)

Bandit 1.9.4 emitted, on every `src/` scan (flagged cosmetic by the
13Sep2026 verification session, queued for a future cleanup wave):

```
[tester] WARNING nosec encountered (B110), but no failed test on file
src/loats/database.py:1720 / 1790 / 1826 / 1852
```

Classified cosmetic by the 13Sep session (informational only); this wave
eliminates it at the root instead.

## Root cause (probe-verified, two-stage)

1. **Misdiagnosis first, corrected by the new net:** an A/B strip
   experiment appeared to show the four annotations inert -- but the
   strip regex never matched (`B1[01]1` does not match `B110`), so the
   experiment was void. The `test_src_scan_has_zero_findings` assertion
   failed on the stripped tree with 4 real B110 findings, proving the
   tokens **load-bearing**.
2. **True root cause:** bandit 1.9.4 attributes B110 to the `try:`
   statement line while the `# nosec B110` token sat on the `except`
   line, so its used-token accounting misses and the note fires even
   though the token suppresses a real finding. The note was a
   line-attribution quirk; the dead-weight was the noisy
   try/except/pass shape itself.

## Fix

The four `try: conn.rollback() / except Exception: pass` blocks in
`src/loats/database.py` -- the Rule-7 terminal-status reset inside
`update_order_status` plus `increment_modification_count`,
`decrement_modification_count`, and `reset_modification_count` --
became `with contextlib.suppress(Exception): conn.rollback()`:

- behaviorally identical (`contextlib.suppress(Exception)` swallows
  exactly what the bare except-pass swallowed),
- the B110 pattern no longer exists, so no token, no note, no finding,
- `contextlib` import added; no other `src/` file touched.

Probed and deliberately NOT touched:

- `scripts/stress_rule7_concurrency.py:80` `# nosec B110 - cleanup` --
  A/B-verified load-bearing (B110 fires without it), and it is outside
  CI's bandit surface (`src/` only).
- `src/loats/utils/retry.py` `# nosec: B311` -- probe-verified
  load-bearing (bare `random.uniform` fires B311); kept, pinned by the
  new net.
- The eight remaining B110 tokens (`metrics.py` x6,
  `config/settings.py`, `options_math.py`) -- all consuming real
  findings (zero notes attributed to those files across every scan).

## Regression net

`tests/test_bandit_nosec_currency.py`: 3 tests, born RED (1 failed with
exactly the four note lines, 2 passed; live run documented above).
Contract pinned:

1. zero `nosec encountered` notes on the `src/` scan (any note = dead
   token or the attribution quirk = scan noise),
2. zero bandit findings on `src/` (the assertion that caught the
   misdiagnosis; CI-parity contract),
3. `retry.py` B311 annotation presence (load-bearing crypto
   suppression must stay).

One scan, module-cached; report written to the system temp dir, never
the repo root (hygiene-ceiling discipline).

## Verification state (measured, repo venv, base 2ef3e39)

- Currency net (3 tests) with the rule7/dual-write files (18+1+3):
  25 passed, rc=0
- Static gates (repo venv first on PATH): ruff check rc=0, ruff format
  rc=0 (after 1-file reformat of the new test), isort rc=0, flake8
  rc=0, mypy `src/ --strict` clean (38 files), bandit rc=0
- `bandit -r src/ -c pyproject.toml -f screen`: **0 notes, 0 issues**
- pip-audit `--ignore-vuln PYSEC-2026-3740` rc=0 (0 vulns, 1 ignored =
  ADR-0010-waived nltk advisory); safety check (pinned 3.8.1) rc=0
  (known deprecation banner = standing monitor 2, unchanged); gitleaks
  rc=0, no leaks
- Full suite with coverage (background, through the conftest guard):
  **1832 passed, 1 skipped, rc=0, total coverage 88.91%**, 8m01s
  (baseline pre-wave: 1829 passed / 88.85% -- the +3 are this wave's
  currency net) -- recorded live during this wave
- Entry-point smoke: `loats --help` rc=0; bare `import loats` resolves
  `src/loats/__init__.py`

## Behaviour contract

- No observable change for any caller: same swallow semantics, same
  logged errors, same fail-closed exceptions.
- The only observable difference: `bandit -r src/ ...` stderr is now
  free of the four WARNING notes; the CI JSON-metrics gate contract is
  unchanged (it gated on findings, which stayed 0 throughout).

## Ceiling protocol

Single-source re-pin per F8-L-07/ADR-0009, split across the wave's
two commits: 414 -> 415 (test net) in the code commit, 415 -> 417
(this record + ADR-0015, +2) in the records commit; the ratchet
history block carries both bumps.
