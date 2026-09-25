# ADR 0019: CMP Supersession Register

## Status

Accepted — 2026-09-23 (FR9 Wave 4 · F9-L-05 / TODO-17)

## Context

FR9 (F9-L-05, Certain) recorded that the build's deviations from the plan
(`LOATS-CMP-13July2026.txt`) are scattered across fifteen-plus ADRs,
amendments, and audit-history records. The chain's own reviews kept
re-deriving the delta by hand: "threshold amendments live where?", "was the
flat layout ever accepted formally?", "which CMP clauses are consciously
different and which are bugs?" The F9-H-01 incident made the cost concrete —
a threshold drifted from CMP text silently precisely because no single
surface answered "what is deliberately different, and by what authority?"

The supersession inventory at the time of this ADR:

| # | CMP expectation | Delivered reality | Authority |
|---|---|---|---|
| S-01 | Cycle < 100 ms hot loop | 8.0 s producer window; budget decision deferred to the 30Sep checkpoint | ADR-0016; R-01 in `docs/RISK-REGISTER.md` |
| S-02 | IV-rank gate math | Chain-IV rank over 252-day series; loud `insufficient_history` fail-closed (silent 0.5 fallback killed) | F9-C-01/F9-M-04 resolution, 15Sep2026 |
| S-03 | Composite 0.6 / opposition 0.4 | Restored to CMP values after silent drift to 0.5/0.6 | F9-H-01, PRs #62/#63 (`9f82a21`), ADR-0016 §Context |
| S-04 | P3 sentiment: RSS+VADER ensemble, 4 h half-life decay, scores bounded [-1,+1] | Delivered (news leg); social 30 % leg deferred pending a real producer | ADR-0017, PR #66 (`633daae`); R-04 residual |
| S-05 | Analyzer decision-intake endpoint | Audited-attempt semantics instead (no endpoint) | ADR-006 Amendment 7, PR #56 |
| S-06 | §4 strike spec: delta 0.50–0.60 buy; SELL 2σ; OI check | Restored/conformed | F9-M-05, PR #55 (`7014186`) |
| S-07 | Producer window semantics | 8.0 s window with timeout+exception cancellation, 50 ms settle grace | ADR-0006 trail, ADR-0007 |
| S-08 | `ta` library | Dropped; numba Supertrend | ADR-0003 |
| S-09 | py_vollib option math | Hand-rolled Black-Scholes | ADR-0004 |
| S-10 | Scheduler signal-engine cadence | Retired; single engine | ADR-0005 |
| S-11 | Repository layout | Flat `src/loats/` layout accepted | FR-wave acceptance records (01Sep matrix) |
| S-12 | Kill switch: THROTTLE→PAUSE→KILL escalation | Binary kill switch + OPS limiter as de-facto throttle; 3-state machine deferred to a PRE-LIVE gate | ADR-0020 |
| S-13 | Audit trail chaining | SHA-256 chain (`previous_hash` link) restored to conformance | F9-M-01, PR #54 (`5f634ba`) |

## Decision

1. **One register, one home.** `docs/CMP-SUPERSESSION-REGISTER.md` is the
   single authority for "where the build deliberately differs from CMP
   text, and why that is legitimate." Every row carries: the CMP
   expectation, the delivered reality, and the authority document (ADR /
   PR / resolution record).
2. **Maintenance rule (binding):** any change that departs from CMP text
   lands WITH its register row in the same PR. A deviation without a row
   is, by definition, an unplanned drift — treat it as a defect finding,
   not a decision.
3. **Review protocol:** every forensic review (FR-chain) reconciles against
   this register first; only register-absent deltas are findings.
4. The register is content-pinned by
   `tests/test_cmp_supersession_register.py` (existence, table shape, and
   the minimum authority set ADR-0002…ADR-0020), so deleting or gutting it
   fails CI visibly.

## Consequences

- **Positive**: the next reviewer starts from the delta instead of
  re-deriving it; silent drift (the F9-H-01 class) becomes structurally
  visible; the FR9 remediation ledger is auditable from one surface.
- **Negative (accepted)**: one more living document to maintain — bounded
  by the same-PR rule, which caps drift at zero by construction.
- **Scope**: no runtime behavior change; documentation + test pins only.

## References

- FR9 report §4, F9-L-05 (`docs/audit-history/15Sep2026-FR9-forensic-review-report.md`)
- ADR-0003, 0004, 0005, 0006, 0007, 0016, 0017, 0018 (rows S-01…S-12)
- ADR-0020 (kill-switch escalation acceptance — row S-12)
