# ADR-0021: Amend the CMP cycle-latency budget to the measured architecture (R-01 decision (b))

- **Status:** Accepted
- **Date:** 2026-09-30
- **Decision owners:** ADR-0016 reserved the (a)/(b) branch to the user; the
  user selected (b) at the 2026-09-30 P5 checkpoint ops window.
- **Supersedes:** ADR-0016 §Decision.1 (the deferral) — the freeze expires
  with this decision. ADR-0016 §Decision.2/§3 (the advisory gate and the
  per-stage collector budgets) remain in force; §Decision.2's promotion
  clause executes in the same wave.

## Context

ADR-0016 (2026-09-17) deferred the cycle-latency budget decision to the
2026-09-30 P5 checkpoint and staged the decision inputs. The designated
evidence stream and the checkpoint-time state:

- **Runner-side:** the advisory `benchmark-perf` job has been green on 15
  consecutive `main` runs (2026-09-28 through 2026-09-30, run
  `36662564397` latest). The 25Sep evidence pack
  (`docs/audit-history/25Sep2026-r01-benchmark-evidence-pack.md`) recorded
  7/7 green with 10/10 stage operations passing and a 13.15 ms ANALYZE
  round trip (~7.6x headroom on the 100 ms round-trip budget).
- **Live cycle span:** 0/26,413 cycles compliant at the 25Sep probe and
  0/1,278 on the gen14 span at the checkpoint probe (avg 3.84 s, max
  11.69 s, kill switch inactive, 5/5 source breakers healthy). Every
  stage the benchmark isolates meets its own budget; the compliance gap
  is entirely the bounded 8.0 s producer window
  (`producer_window_seconds`, ADR-0006/ADR-0007 trail) riding the cycle —
  an architectural characteristic, not a stage regression.
- **Branch (a)** (producer decoupling, background tasks + last-known-good
  snapshots) is a producer-path change; executed mid-span it would
  contaminate the gen14 evidence the checkpoint grades (ADR-0016 §4
  already routes its mechanics into the post-checkpoint producer wave).

## Decision

1. **Option (b): ADR-amend the CMP budget to the measured
   characteristics.** The compliant cycle budget is **1.0 s** (the 1 Hz
   cycle cadence), replacing the unreachable legacy 100 ms compliance
   target. The stage budgets are unchanged and remain enforced by the
   collector: TA 80 ms, DB 20 ms, ANALYZE round trip 100 ms
   (`scripts/collect_p1_phase_gate_evidence.py`, ADR-0016 §3).
2. **Single enforcement source.** `src/loats/latency_budget.py` pins the
   derived constants (`CYCLE_COMPLIANCE_TARGET_SECONDS = 1.0`,
   `PRODUCER_BUDGET_WARNING_SECONDS = 0.080` — the producer warning
   threshold equals the TA stage budget, replacing the pre-window
   30/40 ms noise class). `metrics.record_cycle_time` compliance
   counting and `TradingOrchestrator.get_cycle_stats` compliance
   reporting read the constant; the five producer budget warnings in
   `orchestrator.py` read `PRODUCER_BUDGET_WARNING_SECONDS`. No
   enforcement surface hardcodes a budget number any more.
3. **Same-wave `benchmark-perf` promotion.** The job is renamed to its
   enforcement name `benchmark-perf (F9-H-02 gate)` — green FIRST, then
   promoted into the branch-protection required-context list (10 → 11
   contexts) per ADR-0016 §Decision.2 and the CONTRIBUTING context rule,
   in the same wave as this decision.
4. **Option (a) sequencing unchanged.** Producer decoupling (background
   producers, last-known-good snapshots, degraded tagging) folds into
   the post-span producer wave after 2026-10-13 (ADR-0016 §4): one
   mid-span producer change remains one too many while gen14 accrues.
5. **No mid-span producer-path or settings change.** This decision moves
   measurement-side enforcement constants only; the producer execution
   path, the 8.0 s window, and every trading setting are untouched while
   gen14 runs to its 2026-10-13 14:18Z close.

## Supersession-register riders (same wave, ADR-0019)

- **S-14** (§1/§7 latency-gate surfaces): the five producer budget
  warnings now derive from `PRODUCER_BUDGET_WARNING_SECONDS` per §2 —
  row flips to SUPERSEDED citing this ADR.
- **S-15** (trailing ratchet exercise): the SL-M fixture legs land in
  this wave's test set; supervised enablement of
  `enable_trailing_stops` remains a post-checkpoint supervisor touch.

## Consequences

- **Positive:** the compliance metric is reachable and meaningful again —
  `target_compliance_count` counts cycles inside the amended 1 s budget,
  so the health surface measures real regressions instead of reporting a
  constant 0% against an unreachable target; the producer warnings fire
  on real stage-budget breaches (80 ms) instead of on every producer
  (30/40 ms noise); the benchmark gate becomes a merge-blocking
  required context with a green-reachable verdict.
- **Negative / accepted:** a sub-second budget still cannot absorb the
  producer window, so per-cycle compliance stays data-dependent until
  option (a) lands post-span; cycles whose producers use the full 8 s
  window count non-compliant by design (fail-visible, not fail-hidden).
- **Neutral:** historical counters recorded under the 100 ms target are
  not restated; gen14's span record keeps its measured values.

## References

- `docs/adr/0016-defer-cycle-latency-budget-wire-benchmark-gate.md` —
  the deferral this ADR closes, the advisory gate, the promotion rule
- `docs/audit-history/25Sep2026-r01-benchmark-evidence-pack.md` — the
  staged decision evidence (§2 runner history, §3 live span, §5 runbook)
- `docs/audit-history/25Sep2026-s14-s15-rider-work-orders.md` — the
  rider work orders this wave executes
- `scripts/collect_p1_phase_gate_evidence.py` — the authoritative stage
  budgets (TA 80 / DB 20 / round trip 100 ms)
- `docs/CMP-SUPERSESSION-REGISTER.md` — S-14/S-15 rows

## Amendment (2026-10-05): cycle-FAILURE budget joins the single-source module (M-01)

Audit finding M-01 (05Oct2026): the trading-cycle loop caught every
non-`KillSwitchError` exception, logged it, alerted at most once per
minute, and resumed — a persistent producer fault never failed the
process. Resolution (branch `fix/m01-cycle-failure-budget-05oct`):
`CYCLE_FAILURE_BUDGET` (int, 500) joins this module as the second
single-source enforcement constant, and
`TradingOrchestrator._run_cycle_loop` counts CONSECUTIVE cycle
failures — success re-arms, halted (`KillSwitchError`) cycles consume
nothing — and escalates to a kill-switch activation (the existing
`alerts.activate_kill_switch` primitive: open-orders cancellation +
halt + alert) when the budget is exhausted, instead of another silent
continue. The activation can be refused (fail-closed rollback when the
broker session is dead); the streak then re-arms so a still-persistent
fault re-escalates after another full budget and the loop stays alive
for the operator's own `/kill`. Calibration is evidence-backed: 500
sits ABOVE the largest observed self-healing recovery burst (~350
consecutive breaker-open cycle errors across the 04/05Oct logs —
05Oct 03:00–03:09Z peaked at 46/min, window ~294 total; 04Oct
17:04–17:10Z ~225) so routine circuit-breaker recoveries never trip
the halt, while a genuinely persistent fault escalates in ~8.3 minutes
at the 1 Hz cadence. RED-proven net:
`tests/test_cycle_failure_budget.py` (9 tests). The F9-C-02 routing
divergence counter is untouched — it remains the divergence-path
enforcement that survives the loop.
