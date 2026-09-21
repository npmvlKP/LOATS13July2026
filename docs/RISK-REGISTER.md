# LOATSEV Tracked Risk Register

Living register. The chat/paste transcript is NOT the register: paste lag has
been proven twice (F9-C-02 — the pasted context was already closed at HEAD;
F9-H-03 — the pasted "open High" finding was already closed by PR #65 /
`07ab8ae`). Every status here is reconciled against live repository/system
state at the recorded snapshot before it lands.

Maintenance rules:

- Update this file at every wave close-out; each change lands with the
  evidence that justifies the new status (paths, run ids, measured numbers).
- A risk leaves this file only when its closure is verifiable at HEAD
  (merged commit, passing gate, expired date, or explicit acceptance record).
- Snapshot identity: record the HEAD sha and the scrape/validation timestamps
  used for the update.

Snapshot: HEAD `633daae` (PR #66 merged 2026-09-21T07:06:06Z), post-merge
Pipeline run `35571352961` = success (Docker Build skipped = path-filtered
baseline, identical to run `35550487422`). Register landed 2026-09-21.

| ID | Priority | Category | Status | Due | Next action |
|----|----------|----------|--------|-----|-------------|
| R-01 | P1 | CMP latency decision | OPEN — deferred by ADR-0016 | 2026-09-30 | Decide (a) vs (b) at the checkpoint with the accumulated advisory evidence |
| R-02 | P1 | CMP P5 kill-switch span proof | OPEN — decision required | 2026-09-30 | Approve grader-disclosure amendment (recommended) or accept FAIL-closed |
| R-03 | P2-watch | Benchmark flake | OPEN — watch | on recurrence | py-spy dump protocol on next hang |
| R-04 | P3 | Accepted residual | ACCEPTED | — | Revisit with the post-checkpoint producer wave |
| R-05 | Ops | Environment, dated | OPEN | 2026-10-01 | Shared-venv rebuild; fresh-venv pip-audit replication until then |
| R-06 | Process | Register discipline | CLOSED by this file | — | Maintain per the rules above |

---

## R-01 [P1] Cycle-latency budget decision deferred to the 30Sep checkpoint (ADR-0016)

Category: CMP compliance / architecture decision. Confidence: Certain.

Evidence (2026-09-21, live `:8001/metrics` scrape, span since 16Sep):
`cycle_time_stats` count=2183, `target_compliance_count=0`, average 4.48 s,
max 206.1 s; kill switch inactive. The pasted "0/1501" figure was the count
at the earlier record's snapshot — paste lag, not a discrepancy.

Constraint: ADR-0016 defers BOTH the decision and every enforcement-constant
move until after the 2026-09-30 P5 checkpoint; the producer path and the
100 ms target in `metrics.record_cycle_time` stay untouched mid-span. The
"re-run" therefore cannot legitimately execute before the checkpoint — the
advisory `benchmark-perf` job keeps accruing runner-side evidence on every
push, which is the ADR's designated pre-decision evidence stream.

Next action: at the checkpoint, decide (a) restore a sub-100 ms hot loop by
decoupling producers into background tasks with last-known-good snapshots, or
(b) ADR-amend the CMP budget to the measured characteristics (1 Hz cycle,
bounded 8 s producer window, strike < 5 ms, trail < 1 ms), then promote the
`benchmark-perf` context in the same wave per the documented context-list
rule.

## R-02 [P1] CMP P5 kill-switch proof is not span-attached for pre-guard writer generations

Category: Compliance gate semantics. Severity: High (blocks a PASS verdict
at the checkpoint). Confidence: Certain (verifier output, event-stream
re-derivation).

Evidence (2026-09-21, `scripts/verify_p5_forward_test.py` on the live run
`reports/p5_forward_test_20260916_140341.json`): verdict INCOMPLETE with
`KILL-SWITCH PROOF IS NOT SPAN-ATTACHED ... writer generation(s) 1..3 lack
the verification event`. Event stream: generation 1 is the pre-first-claim
fresh-start window (16Sep 14:03:46 -> 23:24:02); generations 2 (16Sep 23:24
-> 17Sep 23:05) and 3 (17Sep 23:05 -> 19Sep 01:06) closed before the
verification probe existed (P5-OPS-01 landed 2026-09-19). Generations 4..8
each carry their own `kill_switch_verified` event (19Sep..21Sep, latest
21Sep 04:38:09, PID 19836).

Mechanics (from the verifier's re-derivation, the single grading source):
`writer_claimed` opens a generation; only a `kill_switch_verified` event
proves the generation it lands in; a resume probes and proves only the NEW
generation. Generations 1..3 are therefore structurally unprovable in this
artifact — their writers ran pre-guard code that could not emit the event —
and `_grade_span_kill_switch_proof` hard-FAILs an ENDED run that carries any
unproven generation.

Consequence if unaddressed: when the 14-day span ends, the 30Sep grading
checkpoint reads FAIL on the kill-switch criterion even though the halt
primitive has been proven operational in every generation since the probe
existed (and `kill_switch_verified=true` at top level). Demanding the event
from a writer that could not emit it demands the logically impossible;
"unprovable" is not "failed".

Options:
1. (Recommended) Grader-disclosure amendment, mirroring the documented-
   outage annotation pattern (annotations are NON-GRADING; an otherwise
   eligible run PASSes with disclosure) and the P5-OPS-01 introduction
   pattern itself (re-derive from the event stream, no schema change):
   generations whose `writer_claimed_at` (or fresh-start window) CLOSED
   before the P5-OPS-01 date become a named disclosure instead of a hole;
   generations open after that date remain strictly graded. Land as its own
   ADR + verifier change + RED/GREEN parity legs (a pre-guard generation
   discloses and stops flipping the verdict; a post-guard unproven
   generation still hard-FAILs), via the standard PR + CI path.
2. Accept FAIL-closed at the checkpoint and carry the disclosure in the
   closure record — honest, but burns the span's otherwise-clean 14-day
   evidence on a semantics artifact rather than a real halt-path failure.

Decision owner: user (the CMP P5 gate contract). Sequencing: R-02 does NOT
touch the measured producer path, so it does not conflict with ADR-0016's
deferral — but it must land BEFORE the run ends.

## R-03 [P2-watch] Benchmark intermittent hang

Category: Reliability / CI. Status: did not reproduce in prior attempts.

Evidence: historical single-occurrence hang in the benchmark path;
`benchmark-perf` CI job passing on every recent run (run `35563019610` 34 s;
post-merge run `35571352961` success).

Next action: on recurrence, capture a `py-spy dump --pid <pid>` (and
`py-spy record` if interactive) before killing the process; attach the dump
to the incident record.

## R-04 [P3] Accepted residuals — cold-start first-cycle timeout; social 30% leg deferred

Category: Accepted residual. Status: ACCEPTED by design decision.

Evidence: first cycle after a >= 900 s cold start may self-timeout once
(fail-open by design). Social-sentiment 30% leg (CMP news 70 / social 30)
deferred pending a real producer; amendment path documented in ADR-0017.
F9-H-05's ensemble semantics (PR #66, `633daae`) delivered the scoring
machinery toward that leg.

Next action: fold both into the post-checkpoint producer wave (ADR-0016
option (a) mechanics share their machinery with it — one mid-span producer
change instead of two).

## R-05 [Ops, dated] Shared-venv rebuild 01Oct + push-gate pip-audit workaround

Category: Environment / DevOps. Status: OPEN, dated 2026-10-01.

Evidence: the pre-push pip-audit leg audits the AMBIENT shared venv (sibling
projects included); the ~2026-09-17 advisory-DB refresh made it fail pushes
closed even for a blameless declared closure. Standing remedy (proven PR
#51): replicate CI's exact recipe in a fresh temp venv (`python -m venv` ->
`pip install --upgrade pip` -> `pip install .` -> `pip-audit==2.10.1
--ignore-vuln PYSEC-2026-3740`, project-floor Python), document the
replication in the PR body, push `--no-verify`; the PR's required pip-audit
context judges the declared closure authoritatively.

Rules: NEVER mutate the shared venv mid-span (the P5 supervisor runs on it);
rebuild the shared venv on 2026-10-01, then retire the fresh-venv workaround
for subsequent pushes.

## R-06 [Process] Register discipline

CLOSED by this file. The register now lives in-tree at `docs/RISK-REGISTER.md`
and is maintained per the rules in the header. Chat/paste content is
treated as transcript-level claims and reconciled against live state
(git log / gh / live scrapes) before any action — the standing pattern that
caught both paste-lag incidents.

Closed-in-prior-waves reference (kept for provenance): F9-H-03 sentiment
producer (per-day signal table showed the producer effectively dead; closed
by PR #65 `07ab8ae` — per-TTL tier stores, `DEGRADED_THRESHOLD_SECONDS=600`,
unconditional conftest clear; coverage 89.32% at close-out). F9-H-05 CMP P3
ensemble semantics and hard score bounds closed by PR #66 `633daae` with
ADR-0017.
