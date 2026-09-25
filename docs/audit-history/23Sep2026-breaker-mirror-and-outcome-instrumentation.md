# 23Sep2026 — 30Sep Wave: Breaker-Mirror Reset + Signal-Outcome Instrumentation

**Scope:** the two registered 30Sep-wave engineering items, executed on branch
`fix/breaker-mirror-reset-and-outcome-instrumentation`, 2026-09-23, against
HEAD `80c68d9`:

1. sticky per-source breaker-mirror reset (phantom-open `:8001` metrics);
2. signal-outcome instrumentation — the evidence loop for the ANALYZE
   horizon's >=80 % positive-outcome signal gate (user horizon lock,
   2026-09-23; ADR-0020 context; CMP supersession register discipline).

Both findings were live-verified against the repository before any change:
the paste transcript's F9-H-05 entry was RECONCILED FIRST and found already
closed (PR #66, `633daae`, ADR-0017) — not re-executed. PR #72 (FR9 Wave 4)
remains the merge-order predecessor: it carries
`docs/CMP-SUPERSESSION-REGISTER.md` (S-01…S-15) and the L-03 purge script;
this wave touches neither file, so the branches merge cleanly in either
order but the register lands only after #72.

## 1. Sticky breaker-mirror reset (orchestrator.py)

**Root cause (Certain, code-read + RED-proven):** `_guarded_source_get`
wrote `set_circuit_breaker_status("source:{source}", True)` inside the
`CircuitBreakerOpenError` handler and there was NO `False` write anywhere
in the module — the :8001 gauge flips open on the first per-source
degradation and stays flagged open across the breaker's own
OPEN -> HALF_OPEN -> CLOSED recovery, until process restart (phantom-open
operator metrics; RUNBOOK "Circuit Breaker Status" reads wrong).

**Fix:** every successful pass-through now clears the mirror
(`set_circuit_breaker_status(..., False)`) — the success AFTER recovery is
the recovery proof; redundant clears are harmless gauge writes. The fix
itself initially shipped as a `try/except/else` where the `else` suite was
dead code (a `try` exiting via `return` never runs the `else` suite) —
the RED-proven net caught it before commit; the shipped shape is
sequential fall-through with the dead-`else` trap documented in-source.

**Verification (RED-proven net, `tests/test_breaker_mirror_lifecycle.py`):**
success pass-through writes False (pre-fix shape: no write at all — RED);
degradation writes True (pre-existing pin kept); full lifecycle
3 failures -> OPEN-rejection (mirror True) -> open-timeout expiry ->
HALF_OPEN probe success -> CLOSED (mirror False) through the REAL registry
breaker with config save/restore in `finally` (the registry is a
process-wide singleton — a swapped config without restore leaked into
`test_per_source_breakers` during development and was caught by the suite
run: order-sensitivity, fixed).

## 2. Signal-outcome instrumentation (the >=80 % gate's evidence loop)

**Gap (Certain):** the ANALYZE horizon's success criterion is a
positive-outcome signal gate, but the build recorded signals and market
data with NO linkage — no outcome row, no resolver, no verdict surface;
the gate had no evidence loop.

**Design (delivered):**

- `src/loats/signal_outcomes.py` — PURE grading core (no I/O, injected
  clock, deterministic): `SignalOutcomeState`
  (OPEN/POSITIVE/NEGATIVE/NON_DIRECTIONAL/UNRESOLVABLE),
  `evaluate_signal_outcome` (direction x sign of close-to-open over
  independently recorded 1d bars; entry = first bar's open, exit = last
  bar's close, excursion envelope = max high / min low),
  `parse_signal_type` (invalid enum -> None, fail-closed),
  `validate_signal_outcome_horizon` (clamped 1..1440, non-int/bool -> 60).
- `database.py` — `signal_outcomes` table (separate from `signals`:
  producer re-emission is an INSERT OR REPLACE upsert that would clobber
  outcome columns; lifecycle disjointness is the point), sync
  `record_signal_outcome_open` / `resolve_signal_outcomes` (JOIN scan of
  OPEN rows with elapsed horizon; terminal writes are guarded
  `UPDATE ... WHERE outcome_state='open'` so the FIRST verdict wins and
  re-runs are no-ops even across processes) + `get_signal_outcome_summary`
  (positive_rate divides by the DIRECTIONAL denominator only —
  NON_DIRECTIONAL/UNRESOLVABLE never dilute the gate), pool-aware
  `async_*` wrappers.
- `database_async_additions.py` — pool-native `_async_record_signal_outcome_open`
  (mirrors `_async_create_signal`), thread-offloaded resolve/summary
  (F8-H-04 precedent; single code path so a verdict cannot differ between
  pool and non-pool deployments); registered in `extend_database_class`.
- `orchestrator.py` — `_track_signal_outcome_open` called at ALL THREE
  directional emission sites (TA, sentiment, volatility) after the signal
  write: detached task, clamped horizon, HOLD/NEUTRAL skipped (they are
  NON_DIRECTIONAL by the resolver), failures degrade to WARNING —
  instrumentation can never fail the producer path. Resolution runs on
  the cycle loop behind a 900 s monotonic throttle
  (`_maybe_resolve_signal_outcomes`, best-effort) and once more at
  shutdown (flush the final in-flight window).
- Honesty semantics (the gate's integrity): no bars in the horizon window
  -> stays OPEN (never fabricated); horizon not elapsed -> waits;
  invalid signal type / timestamp -> UNRESOLVABLE (fail-closed); every
  terminal verdict dual-writes to the F9-M-01 sha256 audit chain (chain
  integrity re-verified after outcome writes in the net).

**Found during development (caught by the nets, fixed before commit):**

- resolver v1 scanned `s.timestamp_ms <= now - 48 h` — an eligibility
  INVERSION (fresh signals excluded; only stale ones scanned) and had no
  per-row horizon-expiry gate (fresh rows would grade early). Fixed:
  scan selects already-emitted signals; `now >= timestamp + horizon`
  gates each row.
- local-import omission (`SignalType`) — NameError caught by the first
  E2E probe run against a scratch store.

**Settings:** `signal_outcome_horizon_minutes` (default 60, clamped
1..1440 at the call site), documented in `.env.example`
(`SIGNAL_OUTCOME_HORIZON_MINUTES=60`); `check_env_settings_sync` PASSED.

## Verification (this wave)

- New nets: 53 tests (core 29 incl. 1000-case seeded fuzz + deterministic
  replay + ASCII/TODO gate; DB persistence 13; orchestrator wiring 7 +
  breaker-mirror lifecycle 4) — all green, zero warnings (the
  never-awaited-coroutine class is escalated to error by the repo's
  pytest config; the run is clean).
- Regression battery (databases, as_of_date x2, per-source breakers,
  metrics x2, e2e CMP chain): 202 passed, and re-run green after the
  singleton-config-leak fix to prove order-insensitivity.
- E2E scratch-store probe: emit BUY -> open row -> pre-horizon stays OPEN
  -> bars recorded -> POSITIVE verdict -> idempotent re-resolve -> summary
  arithmetic (0.5 rate on 1-pos/1-neg, HOLD excluded from denominator) ->
  SELL NEGATIVE leg -> audit chain verified.
- Gates on all touched files: ruff check / ruff format --check / isort
  / flake8 clean; mypy (5 source files, strict config) 0 issues; bandit
  clean; `check_src_ascii` 39/39 (one U+2192 arrow in an in-source
  comment replaced); `check_function_size` clean;
  `check_env_settings_sync` PASSED; gitleaks no leaks (677 commits);
  repo hygiene PASS at the re-pinned ceiling.
- Ratchet: 459 -> 464 (+5: this module + 3 test files + this record),
  re-pinned in `scripts/ratchet_baseline.py` per the ADR-0009
  single-source protocol, with the disposition recorded in its history
  docstring.

## Residuals / sequencing

- PR #72 merges first (review-blocked, structural): the register +
  purge script ride it; this branch carries no conflicting paths.
- The >=80 % gate itself is graded from accumulated live
  `signal_outcomes` data at the 30Sep checkpoint — this wave ships the
  instrumentation the grading reads; it does not pre-grade the span.
- The resolver's bar source is independently recorded `historical_data`
  (1d); per-intraday-horizon granularity rides the post-checkpoint
  producer wave (R-04) without schema change (interval is a query
  parameter, not a column assumption).
