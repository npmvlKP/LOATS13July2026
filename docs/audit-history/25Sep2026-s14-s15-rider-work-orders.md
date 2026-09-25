# S-14/S-15 Rider Work Orders — 30Sep R-01 Decision Wave (25Sep2026 staging)

- **Issue ID:** S-14 (F9-L-01) + S-15 (F9-L-02) rider staging ·
  **Category:** CMP supersession riders · **Confidence:** Certain (all
  surfaces pinned at HEAD `840ffca`, 2026-09-25)
- **Status:** WORK ORDERS ONLY — no code changed by this document. Both
  riders execute ONLY at/after the 2026-09-30 checkpoint: the ADR-0016
  freeze binds every enforcement constant, and ADR-0019 makes a CMP
  deviation without a register row unplanned drift. Staged so the
  checkpoint wave closes both riders in the same pass as the R-01
  decision.
- **Snapshot identity:** HEAD `840ffca` (see
  `25Sep2026-r01-wave-paste-reconciliation.md` §Snapshot for the full
  probe set).

## S-14 — Producer budget-warning thresholds (orchestrator latency surfaces)

**CMP expectation / delivered reality** (register row S-14,
`docs/CMP-SUPERSESSION-REGISTER.md`): §1/§7 latency-gate enforcement
surfaces carry hardcoded producer budget warnings (30/40 ms) while the
design window is `producer_window_seconds=8.0` (ADR-006 trail) — noise
class. Root cause: the thresholds predate the producer-window
re-architecture and were never derived from it.

**Exact surfaces (all THREE move in ONE commit):**

| Site | Path | Current constant |
|---|---|---|
| TA analysis | `src/loats/orchestrator.py:758` | `0.03` (30 ms) |
| Sentiment analysis | `src/loats/orchestrator.py:902` | `0.04` (40 ms) |
| Volatility analysis | `src/loats/orchestrator.py:1045` | `0.03` (30 ms) |

**Resolution rule (bound to the R-01 branch):** thresholds are DERIVED
from the checkpoint decision — the candidate sources are the producer
window semantics (`producer_window_seconds` under option (a)
decoupling) or the restored/amended CMP budget characteristics under
option (b) (stage budgets TA 80 ms / DB 20 ms / round trip 100 ms per
`collect_p1_phase_gate_evidence.py`). The derivation and the chosen
constants are recorded in the decision ADR; the commit does not invent
numbers — it implements the ADR's derivation. The ADR-0016 freeze
forbids pre-pinning the values before the decision.

**Test net:** extend the orchestrator test suite with a pin that asserts
all three thresholds equal the ADR-derived values (read them from the
module — no string-grepping the source), RED-proven by mutating one
constant. Affected suites: `tests/test_orchestrator.py`,
`tests/test_orchestrator_extra.py`, `tests/test_load_latency_integration.py`.

**Register actions (same PR):** flip S-14 to RESOLVED citing the
decision ADR + commit; extend any S-14 content pins in
`tests/test_cmp_supersession_register.py` in the same commit (the
register is content-pinned — a row-text edit without the pin extension
reds the net).

## S-15 — Trailing-stop ratchet exercise (run-log pin + SL-M fixture)

**CMP expectation / delivered reality** (register row S-15): CMP Rule 12
trailing ratchet is implemented and 93 % covered but UNEXERCISED —
`enable_trailing_stops=False` by default and ANALYZE has no positions.
Resolution requires a supervised run to enable it.

**In-repo surfaces (verified at HEAD):**

- `src/loats/trailing_stop.py` — the monotonic ratchet engine with SL-M
  support (history cap at `trailing_stop.py:453`).
- `src/loats/models.py:17` — `OrderType.SL_M`.
- `src/loats/orchestrator.py:2266-2269` — the SL-M emission path
  including `Rule7ModificationLimitError` handling: a trail move that
  hits the broker's Rule-7 modification limit must degrade gracefully
  without corrupting ratchet state — this is the branch the fixture
  must exercise, not just the happy path.

**Deliverables (per the FR9 Wave-4 L-02 disposition):**

1. **SL-M fixture test:** locate the trailing-stop suite under
   `tests/` and add the SL-M fixture legs — (i) monotonic ratchet
   advances to SL-M emission, (ii) a `Rule7ModificationLimitError` on
   the modification path leaves the ratchet state consistent and the
   position protected. If no dedicated suite file exists, add
   `tests/test_trailing_stop_slm.py`.
2. **Run-log pin:** the supervised run's log must show the ratchet
   actually exercised on live positions; attach the log excerpt /
   evidence to the wave's audit-history record as the pin.
3. **Enablement:** `enable_trailing_stops` is a supervised-run flag —
   enabling is a supervisor touch on the live P5 supervisor, sequenced
   AFTER (1) is green, recorded in the run log. It is NOT a repo
   default change and NEVER a mid-span change before the checkpoint.

**Register actions (same PR):** flip S-15 to RESOLVED citing the run-log
evidence + fixture test; extend the S-15 content pins in
`tests/test_cmp_supersession_register.py` in the same commit.

## Shared execution constraints (both riders)

- **Same-PR rule (ADR-0019):** rider code change, register row flip,
  and pin extension land in ONE PR; a deviation without its register
  row is a finding, not a decision.
- **Freeze:** nothing here executes before the 2026-09-30 checkpoint;
  a mid-span threshold change or trailing enablement contaminates the
  span the checkpoint grades (ADR-0016 §Decision.1).
- **Sequencing inside the wave:** execute AFTER the R-01 decision is
  recorded (these riders derive from it); follow the promotion
  sequence and protection drill in
  `25Sep2026-r01-wave-paste-reconciliation.md` §5–§6.
- **Ratchet:** any new test files bump `TRACKED_FILE_CEILING`
  (`scripts/ratchet_baseline.py`, single-source protocol: ceiling edit +
  history line + `pytest tests/test_repo_hygiene.py
  tests/test_todo25_verifier_gates.py` in the same commit).
- **Gates:** the full quality-gate battery per CONTRIBUTING
  (`ruff check .`, `ruff format --check src/ tests/ scripts/`,
  `flake8 .`, `mypy --strict src`, the pinned-suite pytest set, bandit)
  before push; PR-only delivery under the branch-protection contract
  (10 contexts, or 11 after the benchmark-perf promotion lands).

## References

- `docs/CMP-SUPERSESSION-REGISTER.md` rows S-14/S-15 and ADR-0019
- `docs/audit-history/23Sep2026-fr9-wave4-low-tier.md` §L-01/§L-02 —
  the dispositions that scheduled both riders here
- `docs/audit-history/25Sep2026-r01-benchmark-evidence-pack.md` §5 —
  the checkpoint runbook these orders plug into
- `docs/audit-history/25Sep2026-r01-wave-paste-reconciliation.md` —
  this wave's staging pack (sequence, traps, protection drill)
- ADR-0016 — the freeze that gates both riders
