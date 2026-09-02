# ADR 0006: Per-Signal Unknown-Source Exclusion (F8-M-01)

## Status

Accepted — 2026-09-02

Supersedes the batch-fatal reading of TODO-9 (HC-16). Mirrored at
`docs/ADR-007-per-signal-unknown-source-exclusion.md`.

## Context

TODO-9 (HC-16) made `validate_signal_sources` reject unknown source
strings *loudly* — but at **batch granularity**: any single unknown
`metadata["source"]` string in the signal window vetoed every decision in
the cycle (`strength.py`, pre-fix `:316-331`).

Mixed-provenance windows are the normal state of a shared signal table.
A stray untagged emission (exactly the F8-H-03 class: scheduler jobs
writing signals without a `source` key) converted a data-hygiene lapse
into a chain outage scheduled on the producer's clock. The rejection
reason named the offender, but the remedy (fix the producer) was opaque
to operators and the CMP chain stayed locked out until the offending row
aged out of the 10-signal / 5-minute window.

F8-H-03 removed the scheduler signal emitters (the known offender), but
the batch-fatal failure mode remained: any future untagged producer,
partial write, or external writer to the signals table would re-trigger
the lockout.

## Decision

1. **Exclusion is per-signal; rejection is loud only when nothing known
   survives.** A new shared primitive
   `strength.exclude_unknown_source_signals(signals)` partitions a batch
   into known-source signals and distinct offender strings.
   `validate_signal_sources` uses it, then applies the unchanged CMP
   gates (≥ `min_sources` unique sources, diversity ≥ 0.5) to the
   survivors. The batch is rejected as `unknown_source` only when every
   signal is unknown; an empty batch stays a
   `insufficient_unique_sources` case.

2. **The exclusion is loud.** Every offender string logs an
   `F8-M-01:`-tagged warning per occurrence and is reported in the
   returned details (`excluded_unknown_sources`) on pass *and* fail.
   TODO-9's intent — never silently collapse an unknown source onto a
   default — is preserved: HC-16 now probes an **all-unknown** batch for
   the loud rejection and a mixed batch for non-batch-fatal exclusion.

3. **The exclusion holds end-to-end, not only at the gate.**
   `calculate_composite_strength`, `calculate_strength_diversity`, and
   `get_source_strength_breakdown` all call `resolve_source` (which
   raises on unknowns). Pre-fix, validating a mixed batch and then
   computing strength would crash the cycle with `ValueError` — the
   batch-fatal rejection was hiding this landmine. All three now exclude
   unknown sources defensively (and warn), so the exclusion semantics
   are consistent across the engine.

4. **The decision workflow filters once, at Step 0.**
   `TradeDecisionEngine.create_trade_decision` excludes unknown-source
   signals before validation and uses the filtered list everywhere
   downstream — direction selection (`max(valid_signals, ...)`),
   composite strength, and source breakdown — so an unknown-source
   signal can never set a trade direction even when validation passes.

5. **Exclusions and rejections are audited.** The decision path writes
   dual-write (SQLite + JSONL, SHA-256-chained) audit rows via
   `db.async_log_audit`: `EXCLUDE` per cycle with unknown offenders, and
   `REJECT` per rejected batch with the validator details. Best-effort:
   audit-store failures are logged and never cascade into the cycle.
   Writes are skipped under `ENVIRONMENT=test` so unpatched unit tests
   stay hermetic (no writes to `data/loats.db`).

## Consequences

- A stray untagged signal no longer blocks the chain; the known-source
  remainder is validated and can trade. The CMP minimums (≥3 unique
  known sources, ≥0.5 diversity) are unchanged — the HC-15 gate math is
  untouched.
- The offender stays operator-visible in four places: the tagged
  warning, the validator details, the decision metadata, and the audit
  trail — the remedy (fix the producer) is now traceable.
- `scripts/probe_hc16_unknown_source.py` keeps its all-unknown contract
  (exit 0 iff loud rejection with offenders listed) and passes
  unchanged.
- `scripts/fr7_health_check.py` HC-16 gained a companion assertion:
  mixed batch excludes per-signal (F8-M-01) — no batch-fatal veto.
- Eval harness `scripts/eval_f8m01.py` grades the 10-case matrix:
  BEFORE (live-derived from pre-fix tree via
  `scripts/derive_f8m01_before.py`) 3/10 → AFTER 10/10.
- External verifier `scripts/verify_f8m01_external.py` re-checks the
  same facts from a clean process: 12/12.

## Verification Model (the F8-C-01 lesson)

Per the verification model established after F8-C-01 (docs/ADR-005): a green gate is only evidence if the gate measures the
thing the mandate cares about. The BEFORE baseline is re-derived live
from the pre-fix git tree — no hard-coded claims — and the AFTER score
is a live measurement on the current tree. The finding's three
recommended tests map to C1 (4 valid + 1 unknown passes, audited), C2
(3 valid + 1 unknown fails a CMP gate with the exclusion recorded), and
C3 (all-unknown → `unknown_source` with the complete offender list).
