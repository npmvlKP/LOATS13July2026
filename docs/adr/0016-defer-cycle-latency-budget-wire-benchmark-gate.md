# ADR 0016: Defer the CMP Cycle-Latency Budget Decision; Wire the
# Fail-Closed Performance Benchmark Into CI Now

## Status

Accepted — 2026-09-17

## Context

CMP §1/§7 defines latency gates for the orchestrator cycle, the strike
selection, and the trailing-stop driver. FR9 (F9-H-02, Certain) recorded
that the "orchestrator cycle < 100 ms" gate is abandoned de facto:
`producer_window_seconds=8.0` (ADR-006 trail; the legacy 80 ms window
starved producers under real feed latency), live `:8001/metrics` showed
0/816 cycles compliant (average 7.49 s, max 122.6 s), and the repository
carried no CI benchmark gate and no health-check floor on cycle latency.
FR9 requires, EITHER WAY of the underlying decision: wire
`scripts/benchmark_performance.py` into CI as a gate.

`scripts/benchmark_performance.py` already implements the fail-closed
contract this ADR wires: it grades the UNION of the production registry
and the run's own benchmark operations (an empty measurement set can
never grade PASS), converts a non-PASS verdict into a non-zero process
exit, binds an isolated scratch database (no production writes), and
mirrors the authoritative P1/P5 budgets from
`scripts/collect_p1_phase_gate_evidence.py`.

The 2026-09-17 session exposed that the benchmark gate was BORN-RED: the
budget collapse at `ee71d50` graded every operation against BOTH the
20 ms DB budget and the 100 ms round-trip budget, while the collector
pins a THIRD stage budget (TA_GATE_MS=80) for the TA stage.
`ta_calculation` (CPU-bound technical analysis over 500 bars) therefore
failed a 20 ms budget it was never meant to satisfy: measured PARTIAL
9/10, `ta_calculation` p1_pass_rate 0.00 (p95 67.8 ms), process exit 1
-- on the same host that had recorded passing 6-11 ms TA measurements on
2026-09-13/14. The parity net in `tests/test_performance_analyzer.py`
omitted TA_GATE_MS, which is why the class survived review.

The underlying architecture decision remains open and belongs to the
user: (a) restore a sub-100 ms hot loop by decoupling producers into
background tasks with last-known-good snapshots, or (b) ADR-amend the
CMP budget to the measured characteristics (1 Hz cycle, bounded 8 s
producer window, strike < 5 ms, trail < 1 ms). The supervised P5 forward
test is mid-span toward the 2026-09-30 checkpoint; changing the
producer path or moving an enforcement constant mid-span would contaminate
the span the checkpoint grades.

## Decision

1. **The cycle-latency budget decision is DEFERRED** until after the
   2026-09-30 P5 checkpoint. No enforcement constant moves before it:
   the 100 ms compliance target in `metrics.record_cycle_time`, the
   strike/trail benchmarks, and the health-check surface all stay
   untouched. A health-check compliance floor graded against today's
   live span (0/816 compliant) would flip the run red mid-span;
   enforcement follows the decision, not the other way around.

2. **The decision-independent CI benchmark gate ships now**: a
   `benchmark-perf` job in `ci.yml` runs
   `python scripts/benchmark_performance.py` unsuppressed (the verdict
   IS the exit code) on every push/PR and uploads the JSON evidence.
   The job is ADVISORY -- intentionally absent from the
   branch-protection required-context list -- until decision (a)/(b)
   lands; promotion happens in the same wave as that decision and is
   recorded in CONTRIBUTING.md per the documented context-list rule.

3. **Root-cause prerequisite delivered in the same wave**: the CMP
   stage budgets are restored per the authoritative collector. Each
   ANALYZE round-trip stage is graded on its OWN budget
   (`ta_calculation` on TA 80 ms, `db_operations` on DB 20 ms); the
   100 ms round-trip budget continues to apply to the round trip as a
   whole; every other operation keeps the generic rule (fail if EITHER
   budget is missed below the 80% sample pass-rate). The parity net now
   pins all three collector constants and the per-stage mapping, with
   RED-proven mutated-verdict legs.

4. **Producer re-architecture sequencing**: option (a) mechanics
   (producer decoupling, last-known-good snapshots, degraded tagging)
   share their machinery with the post-checkpoint producer wave
   (F9-H-03 sentiment batching); folding the hot-loop work there keeps
   ONE mid-span producer change instead of two.

## Consequences

- **Positive**: latency regressions in the measured operations now fail
  a CI job instead of only printing a summary; the unreachable-green
  state is eliminated (the gate's green is reachable on any host whose
  stages meet their own budgets); the F9-H-02 "benchmark gate absent"
  clause is discharged for both decision branches.
- **Positive**: the advisory job accumulates runner-side evidence on
  every push, so the deferred decision lands with a measured history
  instead of a one-off sample.
- **Negative (accepted)**: as an advisory job it does not block merges;
  shared-runner noise can produce occasional red runs (the verdict
  grades >= 80% of samples within budget, which absorbs ordinary
  jitter, but contention on a runner is still visible). Red advisory
  runs on main are signal to investigate, not merge blockers.
- **Scope**: no settings change, no orchestrator change, no runtime
  behavior change other than the verdict grading of the two ANALYZE
  stages; the P5 span's measured path is untouched.

## Verification

Measured 2026-09-17, exclusive runs (the benchmark is
contention-sensitive; parallel gate load produces false write-path
failures):

- RED leg (HEAD before the fix): `PARTIAL`, 9/10 latency-gate checks
  passing, `ta_calculation` p1_pass_rate 0.00 (p95 67.8 ms against the
  20 ms DB budget), process exit 1.
- GREEN leg (after the stage-budget fix, nothing else changed):
  `PASS`, 12/12 checks (10 registry + 2 benchmark operations), process
  exit 0.
- `tests/test_performance_analyzer.py`: 17/17 (parity net extended to
  all three collector constants + stage map; TestStageBudgetGrading
  proves the 68 ms TA case passes its own budget while a 200 ms case
  fails it).
- `tests/test_repo_hygiene.py::TestBenchmarkGateWired`: 4/4 -- live
  wiring assertion plus three mutated-copy legs (run step removed,
  continue-on-error injected, project install removed) each proven to
  flip the net red.
- CI: the `benchmark-perf` job's first runs on the wave branch and on
  main after merge carry the green evidence (run ids recorded in the
  merge PR description and the session record).

## References

- FR9 forensic report, F9-H-02 (docs/audit-history/
  15Sep2026-FR9-forensic-review-report.md)
- ADR-0006 (producer window cancellation) and the
  `producer_window_seconds` rationale in settings
- scripts/benchmark_performance.py (fail-closed contract)
- scripts/collect_p1_phase_gate_evidence.py (authoritative budgets:
  TA_GATE_MS=80, DB_GATE_MS=20, ROUND_TRIP_GATE_MS=100)
- src/loats/performance_analyzer.py (stage budget map)
- ee71d50 (the budget-collapse commit whose omission this ADR corrects)
