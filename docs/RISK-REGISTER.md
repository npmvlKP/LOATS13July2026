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
Updated 2026-09-21 (same day) by the R-02 wave: R-02 CLOSED by ADR-0018
(grader-disclosure amendment; live grader re-scrape 2026-09-21T09:20Z shows
the KILL-SWITCH PROOF reason replaced by the NON-GRADING pre-guard NOTE;
P5 nets 165 passed).
Updated 2026-09-23: R-07 opened (test-infra: orphaned fixer-hook mutant
sweep after a hard suite kill — incident record
`docs/audit-history/23Sep2026-orphaned-mutant-sweep-recovery.md`, recovery
protocol verified same day at `7e124c3`: 2,162 passed / 1 skipped /
89.48% branch cov / 534s rc=0 single-process; candidates for prevention
(a) process-tree kill and (b) pre-run frozen-tree guard deliberately OPEN,
not one-key). Also: erratum on the F9-H-05 record's §4 surface list
(`test_strength` deleted 2026-07-21 by `bcc09c1`, absent at the wave's
commits; corrected to the 13 surviving modules, tally corroborated by a
394-passed re-run).
Updated 2026-09-23 (FR9 Wave 4, branch `fix/fr9-wave4-low-tier`): the FR9
Low tier (F9-L-01…06) is dispositioned — L-04/L-05 CLOSED by ADR-0020 and
ADR-0019 (CMP supersession register in-tree, content-pinned); L-03's
root-cause guard is live (`src/loats/signal_source_guard.py`, both write
paths) with the audited purge dry-run-verified at 42 rows and `--apply`
staged for an operator-timed maintenance window; L-01/L-02 are formally
scheduled to the 30Sep decision wave (supersession register rows S-14/
S-15 — they are enforcement-constant/supervised-run changes held by the
ADR-0016 freeze, not dropped); L-06 reconciled (`security.yml` runs
inspected green; broker-side idempotency stays carried). Snapshot:
pre-merge branch state, HEAD `80c68d9` + wave files.
Updated 2026-09-24: F9-M-02 (branch protection on `main` absent — third
consecutive review; the 15Sep FR9 row re-confirmed live by a 404 on the
classic REST GET with an admin token) CLOSED — classic branch protection
re-enabled via the REST API the same day. Live proof: GraphQL rule
`BPR_kwDOTXR8vs4E7JrB` (pattern `main`, isAdminEnforced, 1 approving
review, dismiss-stale, the 10 documented required contexts, strict);
direct push to `main` rejected by the remote hook (GH006) with the branch
ahead by one commit. Discovered and documented: GitHub migrated the rule
to unified ruleset storage — the classic REST GET 404s PERSISTENTLY
although the rule is live and enforced, so the GraphQL BPR query (or
`GET /branches/main` -> `protected:true`) is the required verification
surface on this repo (this also explains the 13Sep "404 -> derive ->
collapse" scare). Closure record:
`docs/audit-history/24Sep2026-F9M02-branch-protection-closure.md`.
Snapshot: HEAD `af3d72c` (PR #76 merged 2026-09-24), post-merge Pipeline
run `36016934081` = success. This register update itself landed through
the PR flow under the restored protection — the flow's first end-to-end
pass since re-enablement (relax -> merge -> restore, GraphQL read-back
count=1 / 10 contexts / admin-enforced).
Updated 2026-09-24: F9-M-01-R1 wave on
`fix/breaker-mirror-reset-and-outcome-instrumentation` — the 17Sep F9-M-01
chain was live-broken by the pooled async audit writer (head cache read but
never advanced; 4,578 entries in 23 frozen runs; verifier False since
18Sep). Root cause fixed (single `to_thread` hop under `_audit_lock`, head
advance restored, uuid entry_ids), 9 regression pins added, live trail
re-anchored fail-closed (`scripts/repair_f9m01_chain_head.py`), production
verifier True post-repair. Evidence:
`docs/audit-history/24Sep2026-f9m01-r1-frozen-chain-head-resolution.md`.
No new R-row: fixed at the wave, not an open risk; the watch item is that
PR #73's CI must stay green with the two new/changed writer files.
Updated 2026-09-24: R-08 opened (degraded-duplicate OpenAlgo instance —
the relaunch fails its :8765 WS bind fail-closed yet survives with a
shadowed, double-bound :5000). Second same-day recurrence (first
instance earlier today, duplicate PIDs 34740/36668 per the ops
transcript; second at 15:32:58 IST, duplicate PID 36592 against primary
29116; third at 16:31:53 IST, duplicate PID 34316 behind a
`uv run app.py` wrapper tree, killed with its wrappers the same hour;
fourth at 18:10:29 IST, duplicate PID 792 behind a second `uv run
app.py` launch from the same operator shell (8244), killed with its
wrappers 18 minutes later — see Continuations 3 and 4 in the incident
record). Duplicate verified
zero-inbound, killed; per-port
single-listener topology re-verified (:5000/:5555/:8765 -> 29116,
:8001 -> P5 32968). Root cause pinned in the OpenAlgo checkout
(a51822b4): asymmetric bind semantics — the WS path probes and fails
closed (RuntimeError at `websocket_proxy/server.py:65`), while the
:5000 listener rides the werkzeug stack behind `socketio.run`, whose
server class sets `allow_reuse_address = True`
(`werkzeug/serving.py:710`), so Windows silently double-binds :5000.
Fix candidates (bind-or-exit pre-flight vs runbook port sweep)
deferred to the 2026-09-30 ops-review window. Incident record:
`docs/audit-history/24Sep2026-degraded-duplicate-recurrence.md`. Paste
reconciliation: the same paste carried F9-H-05 as an open High finding
— STALE, closed by PR #66 `633daae` (re-verified at the models: hard
`Field(ge=-1.0, le=1.0)` bounds on both score fields, ADR-0017, the
dedicated ensemble/decay/bounds nets). The ~18:20 IST paste that
surfaced the fourth occurrence re-carried the same stale block.
Updated 2026-09-25: F9-M-02-R1 (drift follow-up on the F9-M-02 closure —
the same silent-drift class, now the second documented instance): a
fresh paste reconciliation found the server-side rule LIVE but DRIFTED
from the documented contract — `strict:false` with 16 required contexts
(the 10 merge-gating contexts plus the six advisory jobs the 24Sep
closure §3 deliberately excluded, two of their pinned names still
carrying `advisory` / `recorded fallback`). No commit explains the
change (server-side-only state). Corrected the same hour by idempotent
PUT of the documented contract (10 contexts, `strict:true`, 1 approval,
dismiss-stale, admin-enforced): the PUT response echoed it verbatim,
the classic REST GET now resolves the rule directly (the 24Sep
"persistent 404" quirk did NOT reproduce; conversely the GraphQL
`branchProtectionRule` field is gone from the schema — verification is
surface-agnostic, re-probe all surfaces before concluding absence), and
a direct push of an empty probe commit was remote-rejected (GH006,
"Changes must be made through a pull request", "10 of 10 required
status checks are expected") with `origin/main` byte-identical
before/after. No new R-row — the standing re-verify-before-trusting-doc
rule is corroborated by this second instance; every review wave must
live-probe protection against CONTRIBUTING's pinned contract and
restore + record on divergence. Record:
`docs/audit-history/25Sep2026-f9m02-r1-protection-contract-drift.md`.
Updated 2026-09-25 (R-01 evidence staging): the ADR-0016 checkpoint
evidence pack landed at
`docs/audit-history/25Sep2026-r01-benchmark-evidence-pack.md` — seven
consecutive green advisory `benchmark-perf` main runs (24–25Sep, artifact
id 10854087767: PASS 12/12, round trip 13.1 ms) plus a live `:8001/metrics`
re-probe (0/26,413 compliant, avg 1.430 s, max 48.24 s, kill switch
inactive, breakers 4/4). No decision taken, no constant moved: the
the ADR-0016 mid-span freeze binds until the 2026-09-30 checkpoint. R-01
row and section updated in place to cite the pack. Same-day protection
probe: zero drift (10 contexts, strict, admin-enforced — 4th consecutive
clean since the F9-M-02-R1 restoration). Snapshot: HEAD `a01e31c` (PR #79
merged 2026-09-25), pre-merge branch state.
Updated 2026-09-25 (evening, 30Sep-wave staging): the checkpoint wave was
STAGED, not executed — the freeze binds until the checkpoint. Landed on
`docs/sep30-r01-checkpoint`: (1) the wave staging pack
`docs/audit-history/25Sep2026-r01-wave-paste-reconciliation.md` —
paste reconciliation (F9-M-03 block in the evening paste is STALE —
resolved 18Sep by ADR-006 Amendment 7 / PR #56; R-01/R-05/R-07/R-08 and
the protection-watch rows are CURRENT), fresh live probes at 17:29 IST
(protection GET field-by-field exact contract match, 5th consecutive
clean; span 27,557 cycles, 0 compliant, avg 1.663 s, max unchanged
48.243 s, kill switch inactive, breakers 4/4), two decision-frame traps
pinned for the checkpoint executor (the required context is the full
`name:` string `benchmark-perf (F9-H-02 prerequisite, advisory)` —
rename ci.yml BEFORE the 11-context PUT; closing R-01 reds
`tests/test_risk_register_current.py::test_p1_items_carry_the_checkpoint_due_date`
— extend the net in the same commit), and the ordered 30Sep execution
checklist including the promotion sequence and the protection drill;
(2) the rider work orders
`docs/audit-history/25Sep2026-s14-s15-rider-work-orders.md` — S-14
surfaces pinned (orchestrator.py:758/902/1045, all THREE move in one
commit, derived from the decision), S-15 deliverables pinned (SL-M
fixture incl. the Rule7ModificationLimitError degradation leg, run-log
pin, supervised enablement AFTER the checkpoint). R-05 stays dated
2026-10-01 and is NOT folded into the checkpoint wave. Snapshot: HEAD
`840ffca` (PR #80 merged 2026-09-25), branch `docs/sep30-r01-checkpoint`
created at the same SHA, zero divergence, upstream verified by
`git ls-remote`.
Updated 2026-09-25 (evening, same-day repair wave
`fix/benchmark-txn-hygiene`): the 12:59 benchmark run at `ba4febd`
graded PARTIAL (8/10) while an exclusive 13:13 re-run of the same
commit graded 12/12 PASS — root-caused to benchmark write-path
poisoning (UNIQUE collision from wall-clock signal ids + failed
INSERTs leaving open transactions that starved sibling writers for the
30 s busy_timeout), NOT a latency-budget regression; ADR-0016 budgets
untouched. Closed as R-09 (see row). Snapshot: HEAD `ba4febd`
(PR #81 merged), branch `fix/benchmark-txn-hygiene`.
Updated 2026-09-25 (evening, follow-up wave `fix/perf-gate-success-rate`
at main `879015c`, PR #82 merged): the post-merge verification run
exposed a SECOND, masked defect — the F9-L-03 insert-time guard
rejected 100/100 focused `signal_round_trip` samples (fixture missing
the `test` provenance tag) and the gate still graded green because
grading ignored the success flag entirely (exceptions record
durations too). Fixed fail-closed: success-rate component in
`validate_cmp_latency_gates` (generic AND stage composition),
test-provenance tag on the fixture; post-fix run zero failures,
PASS, exit 0. Closed as R-10 (see row).
Updated 2026-09-26 (paste reconciliation `fix/sep26-paste-reconciliation`):
the pasted 15Sep FR9 Low-tier block (F9-L-01/02/03) reconciled live at
HEAD `00d5b8c` — L-01/L-02 are the already-staged S-14/S-15 30Sep riders
(freeze-bound, not dropped; STALE as action items), L-03's guard is
in-tree and the DRY-RUN record stands but `--apply` never ran (live store
still carries the STRESS-ORD row; window = operator, post-supervisor,
`--allow-active-writer` is NOT safe). Two work-order ERRATA pinned in
`26Sep2026-paste-reconciliation-F9L-block.md` §2: S-14's census is FIVE
producer surfaces (758/902/1045/1217/1369), not three; S-15's surface is
`orchestrator.py:2264-2285` at HEAD. New R-12 opened: the live P5 span's
decisional leg has zero routed attempts after two full trading sessions —
root-caused strategy-legitimate (every session cycle audited-rejected its
candidates: 24Sep 770 insufficient_strength + 307 gating_rules_failed;
25Sep 102 + 8) — and ends FAIL-closed at the 2026-10-08 earliest close
unless an attempt fires first. Protection watch: 6th consecutive clean
field-by-field read-back. Snapshot: HEAD `00d5b8c` (PR #85 merged
2026-09-26), CI run `36230558303` green.

| ID | Priority | Category | Status | Due | Next action |
|----|----------|----------|--------|-----|-------------|
| R-01 | P1 | CMP latency decision | OPEN — deferred by ADR-0016 | 2026-09-30 | Decide (a) vs (b) at the checkpoint citing the 25Sep evidence pack (`25Sep2026-r01-benchmark-evidence-pack.md`); promote benchmark-perf in the same wave |
| R-02 | P1 | CMP P5 kill-switch span proof | CLOSED by ADR-0018 | — | See the R-02 section below |
| R-03 | P2-watch | Benchmark flake | OPEN — watch | on recurrence | py-spy dump protocol on next hang |
| R-04 | P3 | Accepted residual | ACCEPTED | — | Revisit with the post-checkpoint producer wave |
| R-05 | Ops | Environment, dated | OPEN | 2026-10-01 | Shared-venv rebuild; fresh-venv pip-audit replication until then |
| R-06 | Process | Register discipline | CLOSED by this file | — | Maintain per the rules above |
| R-07 | P2 | Test infra: orphaned mutant sweep | OPEN — candidates deferred | 2026-09-30 | Decide (a) process-tree kill vs (b) pre-run frozen-tree guard |
| R-08 | P2-ops | Degraded duplicate OpenAlgo instance (shadowed :5000) | OPEN — remediated live, fix deferred | 2026-09-30 | Decide bind-or-exit pre-flight vs runbook port sweep; bind-or-exit recommended |
| R-09 | P2-fixed | Benchmark write-path poisoning (failed INSERTs left open transactions; wall-clock ids collided) | CLOSED by `fix/benchmark-txn-hygiene` | — | Same-commit runs at `ba4febd` graded 8/10 PARTIAL (12:59) and 12/12 PASS (13:13): root cause was nondeterministic lock cascade (30 s busy_timeout starvation), not a budget regression. Fixed: `_rollback_on_error` on 15 sync writers, pool-release transaction repair, uuid4 benchmark ids; `tests/test_transaction_hygiene.py` pins it |
| R-10 | P2-fixed | Benchmark gate false-green: sample success rate ungraded; focused signal fixture rejected at insert | CLOSED by `fix/perf-gate-success-rate` | — | Found by the post-merge verification run at `879015c`: the F9-L-03 guard rejected 100/100 `signal_round_trip` samples (fixture lacked the `test` provenance tag) while the gate graded green off the exceptions' durations. Fixed: `validate_cmp_latency_gates` now grades the sample success rate (incl. the stage-gate composition) fail-closed, and the fixture carries `metadata["test"]`; pinned in `tests/test_performance_analyzer.py::TestSuccessRateGate` |
| R-11 | P2-fixed | Stage gates graded a single-sample population (n=1 TA spike graded 26Sep 9/10 PARTIAL; same class 09/17/20Sep) | CLOSED by `fix/benchmark-stage-samples` | — | Under-sampled STAGE gates fail closed (`insufficient_samples`); round-trip harness discards one warm-up call and measures 5 samples/stage, medians reported; pinned in `tests/test_performance_analyzer.py::TestStageGateSamplePopulation` |
| R-12 | P3-watch | P5 decisional-leg accumulation: zero routed attempts through two full trading sessions (span 24Sep→) | OPEN — accumulation deficit, not a code defect | 2026-10-08 | Earliest valid span close 08Oct 08:02Z: an attempt must fire before `ended_at`, else the run grades FAIL-closed on the decisional criterion by design. 30Sep options: record the FAIL-closed evidence (safety-path span) or schedule a successor span after a CMP review of the strength/gating parameters that rejected every candidate (24Sep 770+307, 25Sep 102+8). Evidence: `26Sep2026-paste-reconciliation-F9L-block.md` §3 |

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

Evidence refresh (2026-09-25, pre-decision staging per ADR-0016 §Decision.2):
live `:8001/metrics` re-probe — count=26413, `target_compliance_count=0`
(0.0%), average 1.430 s (was 4.48 s at the 21Sep snapshot), max 48.24 s
(was 206.1 s), min 0.252 s; kill switch inactive; source breakers 4/4
healthy. Advisory `benchmark-perf` job green on seven consecutive main
runs 24–25Sep (latest run `36113777776`, artifact `10854087767`:
overall PASS, cmp_validation 10/10, benchmark_validation 2/2, ANALYZE
round trip 13.1 ms vs the 100 ms budget). Reading: the span is
stabilizing over a 12x larger population, the stage-level gate is
stably green, and only option (a) mechanics can move cycle compliance
above 0%. Full pack:
`docs/audit-history/25Sep2026-r01-benchmark-evidence-pack.md`.

## R-02 [P1] CMP P5 kill-switch span proof — CLOSED by ADR-0018 (2026-09-21)

Category: Compliance gate semantics. CLOSED same day it was raised, via the
commissioned option 1 (grader-disclosure amendment).

Resolution: ADR-0018
(`docs/adr/0018-p5-preguard-killswitch-disclosure.md`) + the 21Sep audit
record
(`docs/audit-history/21Sep2026-p5-preguard-killswitch-disclosure.md`).
Generations that OPENED before `P5_GUARD_CUTOFF`
(`2026-09-19T00:00:00+00:00`, midnight before the first guarded opening)
disclose as NON-GRADING annotations; post-guard and unknown-vintage holes
stay FAIL-closed exactly as P5-OPS-01 pinned them. Live evidence:
`verify_p5_forward_test.py reports/p5_forward_test_20260916_140341.json`
now grades INCOMPLETE (run genuinely ongoing) with
`NOTE: kill-switch span proof: pre-guard writer generation(s) 1..3 opened
before the verification probe existed` replacing the KILL-SWITCH PROOF
reason; the poisoned 12Sep snapshot keeps its FAIL verdict (divergence-void
+ top-level legs untouched). Nets: frozen-infra 20/20 (RED proven at
7 failed first), span-invariants 21/21, full P5 suite 165 passed.

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
ADR-0017. R-02 CMP P5 kill-switch span proof closed 2026-09-21 by ADR-0018
(pre-guard grader disclosure; post-guard holes still FAIL-closed).

## R-07 [P2] Orphaned fixer-hook mutant sweep after a hard suite kill

Category: test infrastructure. Status: OPEN — recovered incident, prevention
candidates deliberately deferred. Confidence: Certain (reproduced 23Sep).

Evidence: hard-killing pytest MID-`TestFixerHooksSpareFrozenEvidence`
orphans its excludes-stripped MUTANT `pre_commit run` child, which keeps
rewriting the frozen evidence trees; the parent's `finally` repair never
fires. The poisoned state compounds: later runs' damage-deltas read empty
(files already ` M` at session start), the mutant test false-REDDs, and no
repair happens — indistinguishable from order-dependence. Measured 23Sep:
87 ` M` frozen-tree files, whitespace-only; recovery via verified
frozen-confinement + `git checkout` + solo mutant-test green. Corollary:
killed `--cov` runs skip the atexit flush, so `--cov-append` merges carried
phantom floor failures (alerts.py 18.3% / backtest_sanity.py 25.3% were
artifacts; single-process 88% / 86%, CI green).

Incident record + recovery protocol:
`docs/audit-history/23Sep2026-orphaned-mutant-sweep-recovery.md`.

Next action: at the 30Sep ops-review window, decide (a) process-tree kill
for suite timeouts (no hook child can outlive its parent) vs (b) pre-run
frozen-tree guard in the mutant test (fails closed on pre-damaged trees).
Neither is one-key mid-span.

## R-08 [P2-ops] Degraded duplicate OpenAlgo instance with a shadowed :5000

Category: live-estate ops / upstream (OpenAlgo checkout). Status: OPEN —
remediated live, root cause pinned, fix deferred to the 30Sep ops-review
window. Confidence: Certain (reproduced four times on 2026-09-24).

Evidence: relaunching `python app.py` while a healthy instance holds the
ports produces a HALF-ALIVE duplicate: the :8765 WebSocket bind fails
closed exactly as designed (RuntimeError, SDK-compat guard), but the
process does NOT exit — Windows lets the Flask listener double-bind
:5000, leaving two `:5000` LISTENING sockets and one broker login shared
by two processes. Occurrences on 24Sep: earlier today (duplicates
34740/36668 per the ops transcript), 15:32:58 IST (duplicate 36592 vs
primary 29116), 16:31:53 IST (duplicate 34316 behind a
`uv run app.py` wrapper tree uv 29640 -> python 4964 -> app.py 34316;
its own log is the 16:32:02-05 excerpt showing healthy module bring-up
followed by the :8765 fail-closed error), and 18:10:29 IST (duplicate
792 behind a second `uv run app.py` wrapper tree uv 9912 ->
python 15960 -> app.py 792 from the same operator shell 8244; its own
log is the 18:11:14-16 excerpt — same signature, plus the 2.0 s
`port_check` grace wait before the fail-closed error). Each duplicate
served nobody
(zero inbound connections — browser SDK session rides the
primary); each was killed and topology re-verified single-listener per
port (:5000/:5555/:8765 -> 29116, :8001 -> P5 32968; probes :5000 200,
:8765 426, :8001 200). Four recurrences in one day strengthen the case
for the bind-or-exit pre-flight candidate.

Root cause: asymmetric bind semantics in the OpenAlgo checkout
(a51822b4) — the WS path probes the port and fails closed
(`websocket_proxy/server.py:65` via `app_integration.py:277`), while
the :5000 listener rides the werkzeug serving stack behind
`socketio.run` (`app.py:1263`), whose server class sets
`allow_reuse_address = True` (`werkzeug/serving.py:710`) — on Windows
that permits a silent second bind. The error text reads fatal; the
process is not. That gap is the defect. If unremediated: SDK clients
can land on the shadowed
listener (order-dependent intermittent failures) and two processes race
one broker session.

Incident record:
`docs/audit-history/24Sep2026-degraded-duplicate-recurrence.md`.

Next action: at the 30Sep ops-review window, decide (a) startup
bind-or-exit pre-flight for EVERY port — any bind failure is
process-fatal, no partial instances (recommended) vs (b) runbook-only
mitigation (start-script port sweep killing stale listeners before
launch). Touches the OpenAlgo checkout, not this repo's src tree.

## R-11 [P2-fixed] Stage gates graded a single-sample population — fail-closed + population repair

Category: benchmark gate integrity / measurement validity. Status:
CLOSED by `fix/benchmark-stage-samples`. Confidence: Certain (reproduced
from 55 stored runs and a live host probe on 2026-09-26).

Evidence: the post-#83 verification benchmark at main `36212f0`
(2026-09-26 07:20 IST) graded PARTIAL 9/10 — the sole failure was
`ta_calculation` measured ONCE at 83.5 ms against its 80 ms stage
budget (`p5_pass_rate` 1.00, `sample_success` 1.00, DB stage 9.0 ms
clean). A warm host probe showed TA at ~6 ms (cold ~11 ms), and the
same log window shows OpenAlgo's 109k-row master-contract bulk insert
churning — first-call warm-up plus host contention, not a latency
regression. Stored-run forensics: the same n=1 spike class graded runs
PARTIAL on 09Sep (21.8 ms), 17Sep (67.8 ms), and 20Sep (34.8 ms) — the
defect predates the R-09/R-10 fixes and would fire again on any noisy
host; the 18Sep 9/10 PARTIAL shows `db_operations` carries the same
exposure. The 25Sep 12:59 8/10 PARTIAL was R-09's DIFFERENT class
(db_p95 65 s starvation) — do not conflate.

Root cause: `measure_analyze_round_trip` measured each ANALYZE stage
exactly once, then `validate_cmp_latency_gates` applied an
80%-within-budget pass-rate rule to a one-element population — an
80% threshold decided by a single CPU-bound sample is a coin flip on
host noise (and would equally green-light a promotion on a fluke).

Fix (fail-closed, both legs): (1) grading — a STAGE-budget operation
below `MIN_STAGE_SAMPLES` (5) is UNGRADEABLE: `overall_pass` False with
an explicit `insufficient_samples` marker, so one noisy sample can
neither block a healthy run nor green-light promotion; (2) measurement
— `measure_analyze_round_trip` discards one warm-up call (side-channel,
not registry-polluting) and accumulates `ANALYZE_STAGE_SAMPLES` (5)
per stage, reporting the per-stage MEDIAN in the round trip while the
gate grades the full accumulated population. Regression nets:
`tests/test_performance_analyzer.py::TestStageGateSamplePopulation`,
`test_roundtrip_harness_accumulates_gate_population` (real-path
subprocess probe), and `test_generate_summary_marks_under_sampled_
stage_benchmark`. ADR-0016 budgets untouched; no behavior change
outside the gate/summary path. Snapshot: HEAD `36212f0` (PR #83
merged), branch `fix/benchmark-stage-samples`.
