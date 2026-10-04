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
| S-01 | Orchestrator cycle < 100 ms hot loop | 8.0 s producer window; CMP budget amended to the measured architecture (1 Hz / 1 s) | ADR-0021 (amends the ADR-0016 deferral); R-01 CLOSED (`docs/RISK-REGISTER.md`) | SUPERSEDED |
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
| S-14 | §1/§7 latency-gate enforcement surfaces | All seven enforcement surfaces derive from `src/loats/latency_budget.py` (cycle 1 s; producer warnings 80 ms = TA stage budget) — the 30/40 ms noise class and the legacy 100 ms compliance literals are gone; RED-proven net in `tests/test_latency_budget_pins.py` | FR9 F9-L-01; ADR-0021 | SUPERSEDED |
| S-15 | CMP Rule 12 trailing ratchet exercised | SL-M fixture legs landed: monotonic advance to SL-M emission, Rule-7 `Rule7ModificationLimitError` degradation (stop state restored + audited refusal + driver continues), multi-position continuation (`tests/test_trailing_stop_slm.py`; fixture EXPOSED and the fix landed a latent aliasing bug — refusal branch now restores the pre-move config). Supervised `enable_trailing_stops` enablement remains a post-checkpoint supervisor touch on gen14+ | FR9 F9-L-02; ADR-0021 wave | OPEN — supervised enablement pending (fixture + fix landed) |
| S-16 | Options analysis scoped to the NIFTY 13July2026 expiry universe (NSE/NFO markets; position limits 5 NIFTY / 3 BANKNIFTY) | Per-segment session/holiday registry support for MCX (09:00-23:30, 4 holidays/yr) and CDS (09:00-17:00, 16 holidays/yr) landed 01Oct2026 (PR #116, `0ce688e`); `ENABLED_SEGMENTS` defaults to `NSE`, so registry support exists; MCX/CDS require operator `.env` configuration; segment-specific strategy engines remain pending (regime/candidate reporting via liquid benchmarks only, `src/loats/market_status.py`); strategy layer remains NIFTY-universe as planned until the follow-up wave | 01Oct2026 operator mandate (MCX + exchange-traded CDS); PR #116 (`0ce688e`); 02Oct2026 market-activation wave (PR #117) | OPEN — per-segment strategy engines pending (registry + config gate landed) |
| S-17 | Boot proceeds with an observational warning when the audit-chain verifier fails (CMP audit-trail integrity treated as a check, not a gate) | Boot REFUSES on failed verification via `AuditIntegrityGateError` raised before the alerts/scheduler/orchestrator legs; `AUDIT_INTEGRITY_BREAK_GLASS` (default false) is the operator's temporary forensic continue — break-glass boots write an `AUDIT_INTEGRITY_BREAK_GLASS` audit row plus an error alert, then remediation via `scripts/repair_f9m01_chain_head.py` and a clean reboot; `ENVIRONMENT=test` skips the refusal so test suites stay hermetic; the scheduler cleanup pass now grades the verifier result (the "verified" evidence line fires only on a pass) | Audit finding C-01 (04Oct2026, P0); CMP rule + S-13 non-negotiable chain posture; record `docs/audit-history/04Oct2026-C01-audit-integrity-boot-gate.md` | SUPERSEDED |
| S-18 | `OPENALGO_MODE` is a label: order placement respects the operator's separately deployed host-mode posture, with mode recorded as a declared deployment knob (no in-process enforcement consumer required) | Mode is a runtime GATE: `place_order`/`place_smart_order`/`modify_order` hard-refuse with `OpenAlgoModeBlockedError`/`OpenAlgoModeArmingError` unless `OPENALGO_MODE=LIVE` AND the `OPENALGO_ARMING` process-env gesture is set (`src/loats/openalgo.py` `_enforce_order_mode_gate`, after the kill-switch check; refusal writes a `BLOCK` audit row); H-01's armed-refusal ask lands on `modify_order` in the same gate so a supervisor mode flip alone cannot reach the broker; RED-proven net `tests/test_order_mode_gate.py` (15 tests) | Audit finding C-02 (04Oct2026, P0 before any live wiring) + H-01 armed-refusal; `docs/COMPLIANCE-MATRIX.md` boundary cell amended 04Oct2026 | SUPERSEDED |

## Reconciliation protocol

1. Forensic reviews enumerate the build-vs-CMP delta from evidence, then
   check each delta against this register.
2. Register-absent deltas are findings (unplanned drift), filed with
   severity per the FR-scale; the closing wave adds the row and the
   authority.
3. State transitions (OPEN→RESTORED/ACCEPTED/SUPERSEDED) land with their
   evidence in the same PR as the underlying change.
