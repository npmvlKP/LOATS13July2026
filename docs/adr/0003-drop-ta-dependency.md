# ADR 0003: Drop `ta` Library Dependency (TODO-27b)

## Status
Accepted — 2026-08-30

## Context
`pyproject.toml` declared `ta>=0.11.0` and `requirements-core.txt` listed `ta`.
`src/loats/ta.py` is a **custom** technical-analysis module implementing
RSI, MACD, ATR, Supertrend (numba-optimized), VWAP, CMF, BBANDS, CCI,
Hurst and ADX from scratch on pandas/numpy. A grep of `src/loats` shows
**zero** `import ta` or `from ta.` that refers to the external library:

```
grep -rn "import ta" src/loats  # only `from .ta import` (internal)
```

The external `ta` package (`ta.wrapper`, `add_all_ta_features`, …) is never
imported. The custom module is intentionally `loats.ta`, not top-level `ta`,
so there is no naming conflict, but the declared dependency is a ghost.

Forensic reports carried this as `F6-L-07` since FR6 (2026-08-15):
> `ta` declared-but-unused (custom indicators instead)

TODO-27b required a drop-or-adopt decision.

## Decision
**Drop** the `ta` library dependency.

Rationale:
1. **Zero usage** — library not imported anywhere; all indicators are custom.
2. **Performance** — custom Supertrend uses numba `njit(cache=True, fastmath=True)` 
   and is benchmarked within the 80 ms orchestrator window; the library's
   generic wrappers are slower and add pandas overhead.
3. **Maintenance** — `ta==0.11.0` last release 2023-10, depends on unpinned
   `numpy`/`pandas`; removing it shrinks attack surface and `pip-audit` scope.
4. **Adoption cost** — replacing custom ATR/Supertrend/VWAP with `ta` calls would
   require ~300 LOC churn, re-validation of every strength threshold, and would
   re-introduce the same ghost-import confusion.

## Consequences
- **Positive**: `pip install -e .` no longer pulls `ta`; `pip-audit` and
  `pip check` are cleaner; `pyproject.toml` / `requirements-core.txt` are the
  single source of truth.
- **Negative**: If a future producer genuinely needs a library indicator not yet
  implemented (e.g., `ta.trend.ichimoku`), we will re-add `ta` as an *adopt*
  with a pinned version and an ADR superseding this one.
- **Scope**: `src/loats/ta.py` remains as the canonical custom module; its public
  alias `ta = technical_analysis` is retained for convenience.

## Alternatives Considered
- **Adopt**: Import `ta` and delegate RSI/MACD etc. to it, deleting custom code.
  Rejected — loses numba optimization and requires re-certifying every signal
  threshold; the library's `ta.momentum.rsi` uses Wilder's smoothing (different
  from our rolling-mean) and would shift `calculate_rsi_strength` breakpoints.
- **Keep as optional**: List `ta` under `[project.optional-dependencies]`.
  Rejected — optional still implies support; better to re-add when actually needed.

## Verification
- `grep -rn "ta>=" pyproject.toml` → no match
- `grep -rn "from ta\|import ta" src/loats` → no library import
- `scripts/verify_todo27_external.py` — suite (b) 4/4 pass
- `pytest tests/test_ta*.py` — 19 tests passed (custom indicators)

## References
- TODO-27b, VOLLIB_MIGRATION_PLAN.md (same pattern for vollib)
- F6-L-07, F7-L-06 (carried)
- `src/loats/ta.py` header: "Implements custom indicators: Supertrend, VWAP, CMF"
