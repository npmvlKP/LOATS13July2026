# F9-H-04 / TODO-5 Resolution Record — `as_of_date` live-cycle wiring: snapshot date derived from the input batch

**Date:** 2026-09-17 · **Finding:** FR9 F9-H-04 (High, P1 — TODO-5)
**Branch:** `fix/f9h04-as-of-date-wiring` (base `main` @ `c6cfeee`) · **Protocol:** STRICT LOATSEV (BUILD → IMPLEMENT → INTEGRATE → REFACTOR → OPTIMIZE → VERIFY → IDENTIFY → ROOT-CAUSE → FIX → TEST → RECHECK → FIX → RE-VERIFY → CONFIRMED & VERIFIED)
**CMP basis:** CMP Rule 8 — explicit input snapshot dating so decisions are reproducible against the data they were computed from.
**Dependencies at execution time:** none (FR9 register lists F9-H-04 as dependency-free, 2–4 h, P1). F9-C-02's dependency list names F9-H-04; that item's exposure to this wave is the closure recorded here.

## Root cause (verified, not assumed)

FR9 evidence re-confirmed on `main` @ `c6cfeee` before any change:

- The entire F8-L-02 half-close plumbing existed and was test-pinned:
  `TradeDecision.as_of_date` model field (`models.py:371`), the engine
  parameter (`trade_decision.py:156`), the nullable SQLite column with
  legacy migration (`database.py:409`, index 22 on both schema paths),
  CREATE audit rows (`new_state`) and ROUTE audit rows (`metadata`).
- The production caller was never wired: `orchestrator.py:556` passed
  `as_of_date=None` unconditionally in the trading cycle. Production
  effect: 0/1,542 decisions carried a date and 100% of ROUTE rows were
  `as_of_date:null` — CMP Rule 8's traceability anchor defeated.
- The pre-F9-H-04 test `test_cycle_without_as_of_date_keeps_records_null`
  (in `tests/test_as_of_date_propagation.py`) pinned exactly this NULL
  behavior as the "live default contract" — the defect was enshrined as
  a contract. Root cause class: a half-close verified at the API layer
  (parameter plumbed, round trip proven) but never verified at the
  production call-site layer; the acceptance test asserted the wrong
  hemisphere of the contract.

## Remediation

1. **Derivation helper** (`src/loats/orchestrator.py`):
   `TradingOrchestrator._derive_history_snapshot_date(bars)` — sibling of
   the F9-C-01 `_derive_chain_snapshot_date` under the same F8-L-02
   semantic family: the zero wall-clock-date invariant. The snapshot
   date is the max bar timestamp of the already-parsed input batch (the
   latest snapshot the data itself attests to); an empty batch yields
   `None` — honest degradation, never a fabricated date.
2. **Call-site wiring** (the CMP step's engine invocation):
   `as_of_date=as_of_date or self._derive_history_snapshot_date(historical_data_objs)`.
   Caller precedence preserved (backtests pin explicitly); the live
   cycle now supplies a data-derived date. The trading-cycle call
   `_execute_cmp_strategy(as_of_date=None)` is unchanged by design —
   the external verifier `scripts/verify_carried_set_external.py` pins
   the orchestrator signature
   `"as_of_date: datetime.date | None = None"`, and derivation belongs
   inside the CMP step where the input batch exists.
3. **Defect-pin superseded**: `test_cycle_without_as_of_date_keeps_records_null`
   is replaced by `test_cycle_without_as_of_date_derives_from_data`
   (derived date lands on the decision) in
   `tests/test_as_of_date_propagation.py`; the caller-wins and
   engine-level-None contracts are preserved unchanged. A supersession
   note explains that the old pin asserted the defect hemisphere.
4. **New acceptance net** (`tests/test_f9h04_as_of_date_wiring.py`,
   7 tests): helper unit contract (out-of-order bars → latest
   timestamp; empty batch → None; T-1 batch records T-1 — explicitly
   not the wall-clock date; single bar), and end-to-end cycle
   acceptance (decision `as_of_date` == max input-batch timestamp;
   CREATE row `new_state` and ROUTE row `metadata` carry the same
   derived ISO value; empty batch leaves records unpinned).

Legacy rows stay NULL (honest backfill rule, per FR9) — no backfill was
attempted; the column remains nullable.

## Verification evidence (measured, this wave)

- RED first: `pytest tests/test_f9h04_as_of_date_wiring.py` on the
  pre-fix tree → 6 failed / 1 passed; the failures assert the exact
  defect (decision `as_of_date=None`; CREATE row `as_of_date: None`).
- GREEN after fix: `pytest tests/test_f9h04_as_of_date_wiring.py
  tests/test_as_of_date_propagation.py tests/test_e2e_cmp_chain.py
  tests/test_orchestrator.py` → **67 passed** (7 new, 11 rewritten-file,
  49 regression surface).
- Full quality-gate net (repo venv, CI-exact commands): ruff check
  (src/tests/scripts + root scope), ruff format --check, isort
  --check-only, flake8, mypy --strict, bandit, tracked-file ratchet,
  repo hygiene, scripts wiring, src-ASCII, deps sync — all PASS; full
  suite + coverage ≥80% PASS. Command-level evidence in the session
  transcript and the wave commit messages.

## Impact

- CMP Rule 8 (traceability): every live decision and ROUTE row now
  carries the snapshot date of the data it was computed from; NULL
  occurs only when the input batch attests no date.
- F9-C-02 dependency satisfied (its dependency list named F9-H-04).
- No observable behaviour change beyond the intended stamping: routing,
  sizing, gating, rejection paths are untouched; the ROUTE row gains a
  populated `as_of_date` metadata field only.
- Ratchet: ceiling 427 → 429 (+1 test file, +1 this record).
