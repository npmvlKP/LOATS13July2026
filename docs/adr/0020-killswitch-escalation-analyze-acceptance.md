# ADR 0020: Kill-Switch Escalation — Binary Switch Accepted for the ANALYZE Horizon; 3-State Machine Deferred to a PRE-LIVE Gate

## Status

Accepted — 2026-09-23 (FR9 Wave 4 · F9-L-04 / TODO-16)

## Context

CMP §4 specifies a graduated escalation ladder — **THROTTLE → PAUSE → KILL**
(discipline cited: MiFID II Art. 17 analog) — for market-operations risk
control. The delivered build implements a **binary kill switch**:
`alerts.py` gates `/kill` (activate) and `//resume` (deactivate) behind the
admin allow-list; all order paths, the orchestrator cycle, and Telegram are
TLS-wrapped and switch-checked; the OPS limiter (3 req/s) acts as a
de-facto throttle. FR9 (F9-L-04, Certain) recorded the ladder's absence and
offered two resolutions: an ADR acceptance for the ANALYZE horizon, or
building the 3-state machine if LIVE filing is anticipated.

The user locked the system horizon on 2026-09-23: **extended ANALYZE-mode
proving ground** (≥80 % positive-outcome signal gate) with LIVE mode
explicitly deferred to a later, separate deliberation. No LIVE filing is
anticipated in the current planning window.

Exposure assessment at the ANALYZE horizon: the system routes **no orders**
(routing default-OFF by design; the P5 span records honest 404-class
attempts). The graduated ladder's regulatory purpose — proportional,
audited de-escalation of *live order flow* — has no live order flow to
protect. The binary switch plus the OPS limiter plus per-source breakers
cover the operational risks that DO exist in ANALYZE (runaway loops, feed
storms, source failures), and the switch is already admin-gated and
audit-logged.

## Decision

1. **ACCEPT the binary kill switch for the entire ANALYZE horizon.** The
   THROTTLE→PAUSE→KILL ladder is recorded as a **deliberate CMP
   supersession** (row S-12 in the CMP Supersession Register,
   `docs/CMP-SUPERSESSION-REGISTER.md`).
2. **DEFER the 3-state machine to a PRE-LIVE gate, not a date.** Building
   it now would deliver unexercisable states (PAUSE's entry/exit
   distinction is meaningless with no entries) — the same
   breaker-on-a-dormant-source noise class the per-source registry
   explicitly refuses (fail-closed on dormant members). The gate opens
   when, and only when, a LIVE-mode deliberation begins; its completion is
   a prerequisite inside that deliberation, alongside the F9-L-06 carried
   items.
3. **PRE-LIVE gate definition (binding for the future deliberation):**
   - THROTTLE: explicit rate-state with its own threshold transitions
     (the OPS limiter remains the enforcement surface);
   - PAUSE: blocks new entries, allows exits, distinct audit action,
     Telegram notification on every transition;
   - KILL: unchanged semantics (blocks all), Telegram notification on
     every transition;
   - transition tests: threshold crossings in both directions; PAUSE
     entry/exit asymmetry; KILL total-block; notification delivery on
     every transition; audit rows for every state change.
4. **Trigger event:** the user's decision to open a LIVE-mode
   deliberation. Until then this ADR's acceptance stands; no scheduled
   work item exists for the ladder.

## Consequences

- **Positive**: F9-L-04 closes honestly at the ANALYZE horizon without
  shipping dead control states; the future LIVE deliberation inherits a
  precise, test-defined specification instead of a CMP sentence.
- **Negative (accepted)**: a CMP-text deviation stands for the horizon's
  duration — bounded by register row S-12 and this ADR's trigger clause.
- **Scope**: no runtime change; documentation only.

## References

- FR9 report §4, F9-L-04 (`docs/audit-history/15Sep2026-FR9-forensic-review-report.md`)
- CMP supersession register row S-12 (`docs/CMP-SUPERSESSION-REGISTER.md`)
- Horizon lock: user statement, 2026-09-23 (recorded in the 30Sep decision brief §1.6)
- Binary switch implementation: `src/loats/alerts.py` (`/kill`, `//resume`, admin allow-list)
