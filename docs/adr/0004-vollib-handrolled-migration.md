# ADR 0004: Hand-Rolled Black-Scholes Replaces `vollib` (TODO-27a)

## Status
Accepted — 2026-08-30 (implements VOLLIB_MIGRATION_PLAN Phase 2)

## Context
`src/loats/options.py` imported:

```python
from vollib.black_scholes import black_scholes
from vollib.black_scholes.greeks.analytical import delta, gamma, rho, theta, vega
from vollib.ref_python.black_scholes.implied_volatility import implied_volatility
```

`pyproject.toml` declared `vollib>=1.0.11` (which pulls `lets_be_rational`,
`cody-special`, `piecewise-rational`, `simplejson`). The `py_vollib` package
in the venv is a **shim** that warns `py_vollib is deprecated; please import
from vollib instead` and re-exports `vollib`. Both `vollib` and `py_vollib`
are effectively deprecated since 2026-07-15 (F7-L-06 carried).

`docs/audit-history/VOLLIB_MIGRATION_PLAN.md` proposed:
- Phase 1 (1–2 h): drop-in replace `vollib` with `py_vollib`
- Phase 2 (4–8 h): hand-roll Black-Scholes (~200 LOC) for zero external dep

The codebase already had extensive fallback logic in `options.py` for when
vollib raised (brentq → newton → 0.2) because `lets_be_rational` is a compiled
extension that is brittle on Windows and on extreme inputs (t→0, sigma→0).

CMP Rule 9 demands `py_vollib`; the project deliberately used `vollib` as its
ecosystem successor with a documented deviation. Both are now debt.

## Decision
**Implement Phase 2 directly**: hand-roll Black-Scholes in `src/loats/options_math.py`
and make `src/loats/options.py` import from it, dropping `vollib` from
`pyproject.toml`, `requirements-core.txt`, and `mypy` overrides.

`options_math.py` (293 LOC) provides:
- `d1`, `d2` (Hull 7th ed, p.294)
- `black_scholes(flag, S, K, t, r, sigma)` — put-call parity via `norm.cdf`
- `delta`, `gamma`, `vega` (scaled ×0.01), `theta` (scaled ÷365), `rho` (scaled ×0.01)
  — **byte-for-byte** same scaling as `vollib.black_scholes.greeks.analytical`
  (verified against Hull examples 17.1, 17.2, 17.4, 17.6, 17.7)
- `implied_volatility(price, S, K, t, r, flag)` — Brent `brentq` with Newton
  fallback, same bracket `[1e-4, 5.0]` and tolerance `1e-5` as before

No `lets_be_rational` compiled extension is required; only `numpy` + `scipy`
(already required). `mypy --strict` passes without `vollib.*` overrides.

## Consequences
- **Positive**: Zero deprecated deps; deterministic pure-Python; no C extension
  build on Windows; ~200 ms faster import (no `pkgutil.walk_packages` shim);
  `pip-audit` clean; `mypy` clean without overrides.
- **Negative**: We own the math; any Hull deviation is our bug. Mitigated by
  parity tests (see Verification) and by keeping `vollib` installed in the
  current venv for cross-validation (not declared).
- **Compatibility**: Signatures match `vollib` (`flag` as "c"/"p", same Greeks),
  so `tests/test_options.py` only needed a try/except import fallback.

## Alternatives Considered
- **Phase 1 only (py_vollib)**: Direct successor, minimal churn. Rejected —
  `py_vollib` shim warns deprecated; would just move the debt, not remove it.
- **QuantLib**: Industry standard, but heavy (Boost, large wheel), complex API,
  significant code churn, and overkill for vanilla European Black-Scholes.
  Rejected per VOLLIB_MIGRATION_PLAN Risk Assessment (High).
- **Keep vollib**: Documented deviation. Rejected — leaves deprecated dep and
  compiled extension in the critical pricing path.

## Verification
- `src/loats/options.py` no longer imports `vollib` (`grep -rn vollib src/loats` → none)
- `pyproject.toml` and `requirements-core.txt` no longer list `vollib`
- `mypy` override `module = "vollib.*"` removed
- Parity vs `vollib` (venv still has it) on 6 vectors:

```
c 100/90/.5/.01/.2  vollib=12.1115814350 math=12.1115814350 diff 3e-11
p 100/90/.5/.01/.2  diff 1e-12
delta 49/50/.3846/.05/.2 diff 4e-13
gamma diff 2e-14
vega diff 4e-13
theta annual -4.30538996455 diff 3e-12
```

- IV round-trip `price=10.450584 → iv=0.200000` diff 2e-7
- `pytest tests/test_options*.py` — 40 tests passed
- `scripts/verify_todo27_external.py` suite (a) 9/9 pass
- `scripts/verify_todo27_eval.py` — V1-3 all pass, before 3/10 → after 10/10

## References
- TODO-27a, VOLLIB_MIGRATION_PLAN.md Phase 2
- Hull, *Options, Futures and Other Derivatives*, 7th ed, Examples 13.6, 17.1–17.7
- `vollib` source: `black_scholes/greeks/analytical.py` (theta ÷365, vega ×0.01, rho ×0.01)
- Forensic: F7-L-06 carried since FR1, F7-C-01 (mypy)
