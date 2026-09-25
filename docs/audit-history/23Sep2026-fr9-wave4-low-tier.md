# 23Sep2026 — FR9 Wave 4 (Low Tier): F9-L-01…L-06 Disposition Record

**Scope:** FR9 forensic report §4 Low-priority findings (F9-L-01…L-06,
TODO-10/11/12/16/17 + carried set). Executed on branch
`fix/fr9-wave4-low-tier`, 2026-09-23, against HEAD `80c68d9`.

## L-03 (TODO-12) — Live-store hygiene: EXECUTED (root cause) + STAGED (data purge)

- **Root cause half (code):** insert-time provenance guard
  `src/loats/signal_source_guard.py` — every signal insert now
  fail-closes on a missing or unknown `metadata["source"]` tag through
  BOTH write paths (sync `create_signal`, aiosqlite pool
  `_async_create_signal`). Documented exemptions:
  `position_conversion` (lifecycle Trade tag — defensive; no Signal
  writer exists today), `benchmark` (benchmarker fixtures), and the
  explicit `{"test": ...}` provenance key for non-production fixtures.
  Pinned by `tests/test_signal_source_guard.py` (28 tests).
- **Data half (audited purge):** `scripts/purge_legacy_signal_rows.py`.
  Dry-run verified 2026-09-23: **42 untagged rows eligible** (42
  sentiment + 1 combined pre-01Sep was the raw count; the combined row
  carries a valid `price_action` tag and is retained — the classifier
  agrees with FR9's census of 42), 1 STRESS-ORD rehearsal row,
  valid-tagged rows retained. Design: dry-run default; exact-population
  preconditions; single-writer window enforced by a metrics-port probe
  (`:8001` answering = a process holds a stale F9-M-01 chain head →
  abort) plus a 10-minute audit-recency probe; verbatim DB+JSONL
  safety copies; **audit-first** dual-write DELETE entries on the
  sha256 chain (43 entries incl. STRESS-ORD); second-instance chain
  verification; JSON record at
  `reports/ai-generated/f9l03-purge-record.json`.
  **Apply is staged for the exclusive maintenance window** (the app was
  live at preparation time; bouncing a mid-span P5 supervisor is an
  operator decision). Execution: stop app →
  `python scripts/purge_legacy_signal_rows.py --apply` → restart.
- **Fixture migration:** production-shaped fixtures across 7 test files
  re-tagged (enum `source` values) or given explicit test provenance;
  the two F8-M-01 corruption probes now construct the pre-guard legacy
  state at the storage layer (the guarded API can no longer produce
  it), preserving the strength-layer exclusion coverage unchanged.
  Policy net: `TestStoreFixturesDeclareProvenance` requires every
  signal-inserting test module to document its provenance policy.
- **Tests:** `tests/test_purge_script_f9l03.py` (12 pins: classification,
  dry-run default, population-drift abort, audited apply, dual-trail
  DELETE entries with chain-link verification, second-instance verify,
  live-writer abort, ASCII gate).

## L-04 (TODO-16) — Kill-switch escalation: CLOSED by ADR-0020

`docs/adr/0020-killswitch-escalation-analyze-acceptance.md`: binary
switch ACCEPTED for the ANALYZE horizon (user horizon lock 23Sep: no
LIVE filing anticipated; routing default-OFF, no order flow to
protect); THROTTLE→PAUSE→KILL deferred to a PRE-LIVE gate with a
binding, test-defined specification. Register row S-12.

## L-05 (TODO-17) — CMP supersession register: CLOSED by ADR-0019

`docs/adr/0019-cmp-supersession-register.md` +
`docs/CMP-SUPERSESSION-REGISTER.md` (15 rows, S-01…S-15, each with CMP
expectation / delivered reality / authority / state). Content-pinned by
`tests/test_cmp_supersession_register.py` (7 pins). Binding same-PR
rule: a CMP deviation without a register row is unplanned drift — a
finding, not a decision.

## L-01 (TODO-10) — Budget-warning noise: SCHEDULED to the R-01 decision wave

The 30/40 ms hardcoded warnings remain (orchestrator.py TA/sentiment/
volatility paths) — deliberate under the ADR-0016 freeze: the fix note
itself binds the thresholds to the F9-H-02/R-01 outcome (derive from
`producer_window_seconds` vs restore CMP values). Both branches land in
the 30Sep decision wave. Register row S-14 keeps the slot visible.

## L-02 (TODO-11) — Trailing default OFF: SCHEDULED to the 30Sep wave

`enable_trailing_stops=False` stands (ANALYZE has no positions; the
ratchet is implemented and 93 % covered). Enabling is a supervised-run
flag (supervisor touch required) — grouped into the 30Sep wave with its
run-log pin + SL-M fixture test. Register row S-15.

## L-06 — Carried set: reconciled

- P1 latency live re-measurement: superseded by the R-01 decision
  process itself (23Sep double-sample: 9.31 s/cycle steady-state,
  mean 9.913 s, in the 30Sep decision brief).
- Broker-side `Idempotency-Key` honoring: not verifiable in-repo;
  remains carried until a LIVE deliberation.
- `security.yml` weekly runs: **inspected this wave** — last runs
  2026-09-20 and 2026-09-14, all `success` (gh run list). Carried item
  discharged.

## Verification (this wave)

- Wave tests: 42 (guard 28 + purge 12 + register pins 7 → 47 across
  three files; net new 47).
- Affected suites (database, async additions, as_of_date ×2, e2e,
  load/latency, performance analyzer, repo hygiene, todo25 verifier
  gates): all green post-migration (189-test run + final confirmation
  run).
- Gates on all touched files: ruff check, ruff format, isort, flake8 —
  clean; mypy `src/ --strict` — 39 files 0 issues; bandit (new modules)
  — clean (B310 avoided by design: loopback probe via `http.client`,
  ADR-0015 discipline).
- Ratchet: 459 → 469 (+10: 9 wave files + this record), re-pinned in
  `scripts/ratchet_baseline.py` per the ADR-0009 single-source
  protocol.

## Residuals

- The purge `--apply` (operator-timed window; command above).
- L-01/L-02 ride the 30Sep decision wave (S-14/S-15).
- F9-L-06 broker-side item stays carried (out-of-repo).
