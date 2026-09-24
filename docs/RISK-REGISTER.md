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
Updated 2026-09-24: R-08 opened (degraded-duplicate OpenAlgo instance —
the relaunch fails its :8765 WS bind fail-closed yet survives with a
shadowed, double-bound :5000). Second same-day recurrence (first
instance earlier today, duplicate PIDs 34740/36668 per the ops
transcript; second at 15:32:58 IST, duplicate PID 36592 against primary
29116; third at 16:31:53 IST, duplicate PID 34316 behind a
`uv run app.py` wrapper tree, killed with its wrappers the same hour —
see Continuation 3 in the incident record). Duplicate verified
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
dedicated ensemble/decay/bounds nets).

| ID | Priority | Category | Status | Due | Next action |
|----|----------|----------|--------|-----|-------------|
| R-01 | P1 | CMP latency decision | OPEN — deferred by ADR-0016 | 2026-09-30 | Decide (a) vs (b) at the checkpoint with the accumulated advisory evidence |
| R-02 | P1 | CMP P5 kill-switch span proof | CLOSED by ADR-0018 | — | See the R-02 section below |
| R-03 | P2-watch | Benchmark flake | OPEN — watch | on recurrence | py-spy dump protocol on next hang |
| R-04 | P3 | Accepted residual | ACCEPTED | — | Revisit with the post-checkpoint producer wave |
| R-05 | Ops | Environment, dated | OPEN | 2026-10-01 | Shared-venv rebuild; fresh-venv pip-audit replication until then |
| R-06 | Process | Register discipline | CLOSED by this file | — | Maintain per the rules above |
| R-07 | P2 | Test infra: orphaned mutant sweep | OPEN — candidates deferred | 2026-09-30 | Decide (a) process-tree kill vs (b) pre-run frozen-tree guard |
| R-08 | P2-ops | Degraded duplicate OpenAlgo instance (shadowed :5000) | OPEN — remediated live, fix deferred | 2026-09-30 | Decide bind-or-exit pre-flight vs runbook port sweep; bind-or-exit recommended |

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
window. Confidence: Certain (reproduced three times on 2026-09-24).

Evidence: relaunching `python app.py` while a healthy instance holds the
ports produces a HALF-ALIVE duplicate: the :8765 WebSocket bind fails
closed exactly as designed (RuntimeError, SDK-compat guard), but the
process does NOT exit — Windows lets the Flask listener double-bind
:5000, leaving two `:5000` LISTENING sockets and one broker login shared
by two processes. Occurrences on 24Sep: earlier today (duplicates
34740/36668 per the ops transcript), 15:32:58 IST (duplicate 36592 vs
primary 29116), and 16:31:53 IST (duplicate 34316 behind a
`uv run app.py` wrapper tree uv 29640 -> python 4964 -> app.py 34316;
its own log is the 16:32:02-05 excerpt showing healthy module bring-up
followed by the :8765 fail-closed error). Each duplicate served nobody
(zero inbound connections — browser SDK session rides the
primary); each was killed and topology re-verified single-listener per
port (:5000/:5555/:8765 -> 29116, :8001 -> P5 32968; probes :5000 200,
:8765 426, :8001 200). Three recurrences in one day strengthen the case
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
