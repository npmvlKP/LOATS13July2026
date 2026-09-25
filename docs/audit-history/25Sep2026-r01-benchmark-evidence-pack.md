# R-01 Pre-Decision Evidence Pack — Cycle-Latency Budget at the ADR-0016 Checkpoint (25Sep2026)

- **Issue ID:** R-01 evidence staging (ADR-0016 §Decision.2 designated evidence stream) · **Category:** CMP compliance / architecture decision support · **Severity:** P1 at the 2026-09-30 checkpoint · **Confidence:** Certain (all numbers live-probed 2026-09-25)
- **Status:** EVIDENCE PACK — stages the decision inputs; makes NO decision and moves NO enforcement constant. The ADR-0016 mid-span freeze stays in force until the checkpoint.
- **Snapshot identity:** HEAD `a01e31c` (PR #79 merged 2026-09-25), local tree clean and in sync; live probes 2026-09-25 ~15:17 IST; GitHub run/artifact ids cited verbatim.

## 1. Purpose and authority

ADR-0016 (Accepted 2026-09-17) deferred BOTH the cycle-latency budget decision and
every enforcement-constant move until after the 2026-09-30 P5 checkpoint, and named
the advisory `benchmark-perf` CI job as the designated pre-decision evidence stream
("the deferred decision lands with a measured history instead of a one-off sample").
This pack consolidates that history and the live orchestrator span so the checkpoint
review can decide between:

- **(a)** restore a sub-100 ms hot loop by decoupling producers into background
  tasks with last-known-good snapshots, or
- **(b)** ADR-amend the CMP budget to the measured characteristics (1 Hz cycle,
  bounded 8 s producer window, strike < 5 ms, trail < 1 ms),

then promote the `benchmark-perf` context to the branch-protection required list in
the same wave per the documented context-list rule (CONTRIBUTING.md).

## 2. Runner-side evidence: advisory `benchmark-perf` job history

Every `Pipeline` run on `main` 24–25Sep carried a GREEN `benchmark-perf
(F9-H-02 prerequisite, advisory)` job — seven consecutive main-branch runs probed:

| Run id | Date (UTC) | benchmark-perf | Overall run |
|---|---|---|---|
| 36016934081 | 2026-09-24 15:00Z | success | success |
| 36076918490 | 2026-09-25 00:18Z | success | success |
| 36079281988 | 2026-09-25 00:49Z | success | success |
| 36080330216 | 2026-09-25 01:03Z | success | success |
| 36081844490 | 2026-09-25 01:24Z | success | success |
| 36095063200 | 2026-09-25 04:35Z | success | success |
| 36113777776 | 2026-09-25 08:35Z | success | success (HEAD `a01e31c`) |

Artifact evidence (run 36113777776, artifact id 10854087767 `benchmark-results`,
44,988 bytes, `expired=false`; report
`performance_benchmark_20260925_083616.json`):

- `summary.overall_status`: **PASS** (fail-closed contract; the verdict IS the exit code)
- `summary.cmp_validation`: 10/10 operations passing (pass_rate 1.0) — registry operations graded on their own stage budgets (TA 80 ms / DB 20 ms per the ADR-0016 §3 correction)
- `summary.benchmark_validation`: 2/2 benchmark operations passing (pass_rate 1.0)
- `summary.analyze_round_trip`: total 13.15 ms (TA 60.8% / DB 39.2%) — the ANALYZE round trip meets the 100 ms round-trip budget with ~7.6x headroom on the runner
- DB stage averages: async write 1.03 ms, async read 0.33 ms, sync write 0.50 ms, sync read 0.28 ms
- 100 latency iterations per benchmark operation

Reading: the in-repo ANALYZE measurement path is healthy and its CI gate is
stably green across a full day of runner-side samples. The gate's green is
reachable and reproducible — the precondition ADR-0016 set for promoting the
context to required.

## 3. Live evidence: orchestrator cycle span (P5 supervisor, `:8001/metrics`)

Live scrape 2026-09-25 ~15:17 IST (span since 16Sep, continuous):

| Field | 21Sep register snapshot | 25Sep live probe (this pack) |
|---|---|---|
| `count` | 2,183 | **26,413** |
| `average_seconds` | 4.48 s | **1.430 s** |
| `min_seconds` | — | 0.252 s |
| `max_seconds` | 206.1 s | **48.243 s** |
| `target_compliance_count` | 0 | **0** (0.0% of 26,413) |
| kill switch | inactive | **inactive** (`kill_switch_active=false`) |
| source breakers | — | 4/4 healthy (`source:ta`, `source:volatility`, `source:price_action`, `source:options_flow` all true) |

Reading (measured, decision-neutral):

1. The 100 ms budget remains unmeetable by the current architecture: **0 of
   26,413 cycles compliant** across the full span, while every stage the
   benchmark isolates individually meets its own budget. The gap is the
   producer window (`producer_window_seconds=8.0`, ADR-006 trail) riding the
   cycle — an architectural characteristic, not a stage regression.
2. The span is stabilizing, not degrading: average fell 4.48 s -> 1.43 s and
   worst-case 206.1 s -> 48.2 s between the register snapshot and this probe,
   over a 12x larger cycle population. No latency excursions threaten the
   supervised run.
3. Option (a) (producer decoupling) is the only branch that can move
   compliance above 0% — consistent with ADR-0016 §4 folding its mechanics
   into the post-checkpoint producer wave. Option (b) legitimizes the
   measured characteristics; on this evidence its amended budget would pin
   approximately: 1 Hz cycle cadence, bounded 8 s producer window, and the
   stage budgets already enforced (strike < 5 ms, trail < 1 ms, TA 80 ms,
   DB 20 ms, round trip 100 ms).

## 4. Snapshot of record (machine-readable)

```json
{
  "snapshot": {
    "head": "a01e31c",
    "probed_at_ist": "2026-09-25T15:17:00+05:30",
    "pack": "docs/audit-history/25Sep2026-r01-benchmark-evidence-pack.md"
  },
  "ci": {
    "main_runs_with_green_benchmark_perf": [
      "36016934081", "36076918490", "36079281988", "36080330216",
      "36081844490", "36095063200", "36113777776"
    ],
    "latest_run": "36113777776",
    "latest_run_conclusion": "success",
    "benchmark_artifact_id": "10854087767",
    "benchmark_report": "performance_benchmark_20260925_083616.json",
    "overall_status": "PASS",
    "cmp_validation_pass_rate": 1.0,
    "benchmark_validation_pass_rate": 1.0,
    "analyze_round_trip_ms": 13.149
  },
  "live_cycle_span": {
    "endpoint": "http://127.0.0.1:8001/metrics",
    "count": 26413,
    "average_seconds": 1.4300106684965705,
    "min_seconds": 0.252293,
    "max_seconds": 48.242796,
    "target_compliance_count": 0,
    "kill_switch_active": false,
    "circuit_breakers_healthy": 4,
    "prior_register_snapshot": {
      "date": "2026-09-21",
      "count": 2183,
      "average_seconds": 4.48,
      "max_seconds": 206.1,
      "target_compliance_count": 0
    }
  },
  "branch_protection_probe": {
    "protected": true,
    "required_contexts": 10,
    "strict": true,
    "approvals": 1,
    "dismiss_stale": true,
    "admin_enforced": true,
    "drift": "none — zero-drift probe, 4th consecutive clean since the 25Sep restoration"
  }
}
```

## 5. 30Sep checkpoint runbook (what this pack feeds)

1. Decide (a) vs (b) against §2/§3 — the pack is the promoted advisory
   evidence ADR-0016 requires the decision to cite.
2. Record the decision as an ADR (amendment to ADR-0016 or a successor
   ADR), updating `docs/CMP-SUPERSESSION-REGISTER.md` rows S-14 (§1/§7
   producer budget thresholds — currently hardcoded 30/40 ms noise class,
   resolution derives thresholds from this decision) and S-15 (trailing
   ratchet run-log pin), which ride this wave by the FR9 Wave-4 disposition.
3. Promote `benchmark-perf (F9-H-02 prerequisite, advisory)` into the
   required-context list in the SAME wave: branch-protection PUT with the
   documented contract plus the promoted context, then pin the new
   11-context list in CONTRIBUTING.md (the register documents the rule; the
   25Sep F9-M-02-R1 wave proves the restore-by-PUT drill).
4. If (a): fold producer decoupling into the post-checkpoint producer wave
   per ADR-0016 §4 (one mid-span producer change instead of two); if (b):
   move `metrics.record_cycle_time`'s 100 ms target and the health-check
   surface as ONE enforcement change, never mid-span.
5. Update `docs/RISK-REGISTER.md` R-01 to CLOSED with the decision record,
   and re-probe protection against CONTRIBUTING's pinned contract (standing
   rule — it drifted twice: 15Sep absence, 25Sep contract drift).

Constraints that still bind until the checkpoint: no enforcement constant
moves, no producer-path change, no mid-span settings change (ADR-0016
§Decision.1; the supervised P5 run grades the untouched span).

## 6. Paste-reconciliation appendix (25Sep evening paste)

Step-0 verdicts on the pasted content that triggered this session:

| Paste claim | Live verdict at HEAD `a01e31c` |
|---|---|
| 🟡 F9-M-03 — analyzer decision-intake deferred, USER DECISION (a)/(b) open | **STALE — RESOLVED 2026-09-18**: option (a) audited-attempt semantics accepted; ADR-006 Amendment 7, PR #56, closure record `docs/audit-history/18Sep2026-f9m03-audited-attempt-semantics.md`; `verify_p5_forward_test.py` already grades under the accepted semantic |
| `wc` not recognized (PowerShell) | Operator shell mismatch, benign — the command ran under PowerShell; `git ls-files | wc -l` works in POSIX shells (this session: 481, at the ratchet ceiling) |
| Prioritized risks R-01/R-07/R-08/R-05 + protection watch | **CURRENT** — matches the register rows verbatim; R-01 evidence staging (this pack) is the one actionable pre-checkpoint item; R-07/R-08 are 30Sep-window decisions, R-05 is dated 01Oct |

No code defect was live in the paste; the wave's deliverable is evidence
staging, not remediation.

## References

- ADR-0016 (`docs/adr/0016-defer-cycle-latency-budget-wire-benchmark-gate.md`) — the freeze, the advisory gate, and the promotion rule
- `docs/RISK-REGISTER.md` R-01 (P1, due 2026-09-30) and the 21Sep live-span snapshot row
- `scripts/benchmark_performance.py` (fail-closed contract) and `scripts/collect_p1_phase_gate_evidence.py` (authoritative budgets TA 80 / DB 20 / round trip 100 ms)
- `docs/audit-history/25Sep2026-f9m02-r1-protection-contract-drift.md` (the PUT-restore drill this pack's protection probe re-used)
- `docs/adr/0020-killswitch-escalation-analyze-acceptance.md` + `docs/CMP-SUPERSESSION-REGISTER.md` S-14/S-15 (items riding the 30Sep wave)
