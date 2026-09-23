# CMP Supersession Register

**Authority:** ADR-0019 (2026-09-23, FR9 Wave 4 / F9-L-05).
**Purpose:** the single surface answering "where does the build
deliberately differ from the plan (`LOATS-CMP-13July2026.txt`), and by what
authority?" Reviews reconcile against this register FIRST; only
register-absent deltas are findings.

**Maintenance rule (binding, from ADR-0019):** any change that departs from
CMP text lands WITH its register row in the same PR. A deviation without a
row is unplanned drift — a defect finding, not a decision.

State legend: **OPEN** (deviation live, resolution scheduled) ·
**ACCEPTED** (deviation live, accepted for the horizon) ·
**RESTORED** (was drift, conformed back to CMP) ·
**SUPERSEDED** (CMP expectation permanently replaced by recorded decision).

| ID | CMP expectation | Delivered reality | Authority | State |
|----|-----------------|-------------------|-----------|-------|
| S-01 | Orchestrator cycle < 100 ms hot loop | 8.0 s producer window; budget decision deferred | ADR-0016; R-01 (`docs/RISK-REGISTER.md`) | OPEN — 30Sep checkpoint |
| S-02 | IV-rank gate math (BUY < 30) | Chain-IV rank over 252-day series; loud `insufficient_history` fail-closed; silent 0.5 fallback killed | F9-C-01/F9-M-04 resolution (15Sep2026) | RESTORED |
| S-03 | Composite 0.6 / opposition 0.4 | Restored after silent drift to 0.5/0.6 | F9-H-01, PRs #62/#63 (`9f82a21`) | RESTORED |
| S-04 | P3 sentiment: RSS+VADER ensemble, 4 h half-life decay, scores bounded [-1,+1] | Delivered on the news leg; social 30 % leg deferred pending a real producer | ADR-0017, PR #66 (`633daae`); R-04 residual | OPEN — residual deferred (R-04) |
| S-05 | Analyzer decision-intake endpoint | Audited-attempt semantics (no endpoint) | ADR-006 Amendment 7, PR #56 | SUPERSEDED |
| S-06 | §4 strike spec: delta 0.50–0.60 buy; SELL 2σ; OI check | Conformed | F9-M-05, PR #55 (`7014186`) | RESTORED |
| S-07 | Producer window semantics | 8.0 s window, timeout+exception cancellation, 50 ms settle grace | ADR-0006 trail, ADR-0007 | SUPERSEDED |
| S-08 | `ta` library | Dropped; numba Supertrend | ADR-0003 | SUPERSEDED |
| S-09 | py_vollib option math | Hand-rolled Black-Scholes | ADR-0004 | SUPERSEDED |
| S-10 | Scheduler signal-engine cadence | Retired; single engine | ADR-0005 | SUPERSEDED |
| S-11 | Repository layout | Flat `src/loats/` accepted | FR-wave acceptance records (01Sep matrix) | ACCEPTED |
| S-12 | Kill switch: THROTTLE→PAUSE→KILL escalation | Binary switch + OPS limiter; 3-state machine deferred to the PRE-LIVE gate | ADR-0020 | ACCEPTED — ANALYZE horizon |
| S-13 | Audit trail SHA-256 chaining | Restored (`previous_hash` link chain + walking verifier) | F9-M-01, PR #54 (`5f634ba`) | RESTORED |
| S-14 | §1/§7 latency-gate enforcement surfaces | Producer budget warnings hardcoded at 30/40 ms while the design window is 8 s (noise class); resolution derives thresholds from the decision | FR9 F9-L-01; ADR-0016 freeze | OPEN — rides the R-01 decision wave |
| S-15 | CMP Rule 12 trailing ratchet exercised | `enable_trailing_stops=False` default; ratchet implemented + 93 % covered but unexercised until a supervised run enables it | FR9 F9-L-02; ANALYZE has no positions | OPEN — rides the 30Sep wave (run-log pin + SL-M fixture test) |

## Reconciliation protocol

1. Forensic reviews enumerate the build-vs-CMP delta from evidence, then
   check each delta against this register.
2. Register-absent deltas are findings (unplanned drift), filed with
   severity per the FR-scale; the closing wave adds the row and the
   authority.
3. State transitions (OPEN→RESTORED/ACCEPTED/SUPERSEDED) land with their
   evidence in the same PR as the underlying change.
