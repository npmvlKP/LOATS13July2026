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
Updated 2026-09-26 (performance-review paste reconciliation): the
pasted 8-row Performance Review table reconciled live at HEAD `f4a80ee`
— every flagged row is already dispositioned: F9-H-02's gate EXISTS in
CI (`benchmark-perf`, exit-code contract, wired 17Sep) and is ADVISORY
BY DESIGN until the deferred R-01 decision (ADR-0016 promotion
deferral; live protection = 10 contexts, no benchmark-perf, exactly as
registered); the strike/trail "benchmarked" mechanism was
misattributed (no strike/trail budgets live in
`benchmark_performance.py`; real surfaces: strike_selection.py:219 +
orchestrator.py:1945 warn-only 5 ms, orchestrator.py:2188 trail budget,
collector constants DB 20 / RT 100 / TA 80 ms); F9-L-01/F9-L-02 are the
S-14/S-15 30Sep riders (freeze-bound, unchanged). All six clean rows
(provider window settle, SQLite WAL+30 s+to_thread, TTL caches, numba
Supertrend, 10 MB rotation, N²/blocking-I/O tail) re-verified in-tree.
P5 span LIVE during probes (mtime 21:49 IST); INCOMPLETE grade is
correct in-progress state. Full verdict table and mechanism
corrections: `26Sep2026-performance-review-paste-reconciliation.md`.
Snapshot: HEAD `f4a80ee` (PR #86 merged 2026-09-26), CI run
`36247737708` green.
Updated 2026-09-26 (console-probe paste reconciliation): the evening
paste's console-probe tail reconciled live at HEAD `d486f75` — the
pasted isort charmap warnings are PROVEN CONSOLE-COSMETIC: the
CI-exact scope grades rc=0 on the canonical venv under a UTF-8 console
(zero warnings) and reproduces exactly 26 warnings under a forced
cp1252 console with the SAME rc=0; glyph content (em-dash, ✓, 🚀, μ,
≈, →, ≤) fails the cp1252 decoder only. Operator guidance pinned:
`python -X utf8 -m isort --check-only src tests scripts`; never strip
glyphs to silence the warnings. The pasted local `pip_audit` finding is
the raw no-ignore-leg invocation; CI pins `--ignore-vuln PYSEC-2026-3740`
(ci.yml:323, ADR-0010 monitor stands). PR #87's fumbled create line and
the PowerShell `<changed paths>` redirect error both resolve to already
merged/verified state (merge commit `d486f75` content-identical to
`a4f94db`, diff empty). Protection: 8th consecutive clean field-by-field
read-back — first watch with NO dismiss_stale derive-gap repair needed.
Full verdict table: `26Sep2026-console-probe-paste-reconciliation.md`.
Snapshot: HEAD `d486f75` (PR #87 merged 2026-09-26), CI run
`36257907490` green.
Updated 2026-09-27 (paste reconciliation, rollover/rebuild window): the
morning paste (OpenAlgo host console, 06:46-06:48 IST) reconciled live
at HEAD `10d410f` — every pasted failure is host-layer, transient, or
stale: the 06:46 auth errors are the designed daily-rollover gap
(self-detected via the empty-funds probe, fresh broker login
06:47:13), the NSE_INDEX token errors fall strictly inside the
master-contract rebuild window (Symtoken deleted 06:47:17, 109,485-row
bulk insert completed 06:47:47, cache loaded 06:47:54 — zero
occurrences in the stream after), and the paste's
Performance/Scalability/Reliability sections are verbatim re-slices of
the 15Sep FR9 report with all four "Open" findings closed upstream
(F9-C-01/S-02 RESTORED, F9-C-02/S-05 SUPERSEDED, F9-M-01/S-13
RESTORED, F9-H-03 closed 20Sep). New LOATS-side observation the paste
did NOT contain: the same window drove LOATS's FIRST breaker storm
(24-26Sep greps: zero occurrences) — global breaker OPEN 01:16:44Z on
the rollover auth gap, 351 fail-closed quote refusals, 35 per-source
OPENED cycles, and 102 guaranteed-404 strikes fetches while the
fallback-expiry hint (`openalgo.py:250-262`, today+7d) emitted a
Sunday expiry (04OCT26) because `/expiry` could not resolve through
the window. Fail-closed worked as designed: zero decisions, zero
fabricated data, P5 span unharmed (`unhandled_exceptions` 0), full
recovery by 01:28:40Z. Opened as R-13 (P3-watch); hardening rides the
30Sep ops window (ADR-0016 freeze binds). Record:
`docs/audit-history/27Sep2026-openalgo-rollover-rebuild-breaker-window.md`.
Snapshot: HEAD `10d410f` (PR #88 merged 2026-09-26), CI run
`36263835750` green.
Updated 2026-09-27 (evening, FR9-sections re-slice reconciliation): the
paste's four review sections (Testing §11, DevOps §12, Maintainability
§9, Code Quality §10) were proven a verbatim re-slice of the archived
15Sep FR9 report — containment 8/8 against
`15Sep2026-FR9-forensic-review-report.md` — and every pasted finding is
already dispositioned upstream: F9-C-01/S-02 RESTORED
(`insufficient_history` live at `rules.py:513`), F9-C-02/S-05 closed
(routing-guard + kill-switch span-proof nets, INVALID-EVIDENCE archive),
F9-M-05 strike band implemented + 28-pin net, F9-H-03 liveness
remediated 17/20Sep, benchmark-perf gate present at `ci.yml:365`
(advisory per ADR-0016), F9-M-02 closed 24Sep, F9-H-01/S-03 conformance
pins live, F9-L-05 closed by ADR-0019. The §10 figures (1841 tests /
88.93 % / mypy 38 files) are the 15Sep session's numbers: session suite
at this HEAD is 2290 passed / 1 skipped (the by-design cov-lock guard
skip; the vollib optional-parity skip did not fire — module present in
the shared venv), branch coverage 89.49 % (7298/8001), mypy strict
clean on 40 files. The wave's one real fix: the R-13 section synced to
the PR #90 row truth-up (register-internal row/section contradiction).
Record:
`docs/audit-history/27Sep2026-fr9-sections-reslice-reconciliation.md`.
Snapshot: HEAD `ea6f78f` (PR #90 merged 2026-09-27).
Updated 2026-09-27 (night, FR9 §13 risk-matrix re-slice reconciliation):
the paste's §13 Risk Matrix proven a verbatim re-slice of the archived
15Sep FR9 report — 13/13 rows containment-true against archive lines
227-243 — and every row dispositioned upstream (F9-M-02 contradicted
live by the protection GET at this HEAD: approving=1, dismiss_stale,
enforce_admins, strict, 10 contexts). The wave's one real finding: R-13's
FOURTH occurrence — a Sunday-evening storm 19:38-20:31 IST
(14:08:49-15:00:50Z), 85 OPENED events (17 cycles x 5 breakers), 3,373
fail-closed refusals, zero decisions, zero P5 residue, self-healed; the
19:55 host console restart in the paste landed MID-STORM. Record:
`docs/audit-history/27Sep2026-fr9-riskmatrix-reslice-reconciliation.md`.
Snapshot: HEAD `a2991c2` (PR #91 merged 2026-09-27).
Updated 2026-09-28 (00:46 IST paste, FR9 §11/§12 re-slice
reconciliation): the ninth family member re-sliced the archive's
Testing/DevOps sections — containment 12/12 verbatim fragments against
`15Sep2026-FR9-forensic-review-report.md` lines 221/225, with §13 again
byte-identical to the 23:18 paste (25/25 normalized lines). Every
era-claim dispositioned: F9-M-02 contradicted live (GraphQL
approving=1, dismiss_stale, admin-enforced, 10 contexts — ninth
consecutive clean read-back), benchmark-perf present at `ci.yml:365`
(advisory; R-01 owns promotion at the 30Sep window), the 15Sep report
itself already relocated to `docs/audit-history/`, security.yml runs
inspected green (FR9 Wave 4). The pasted `--body-file <file>` PS 5.1
ParserError was reproduced live and died at parse time — the intended
PR create succeeded as PR #92 (merged `4201a02`, branch purged,
post-merge run `36341230913` green). No new findings: zero breaker
events after the 15:00:50Z recovery (R-13 stays at four occurrences),
P5 span live (529 cycles, kill_switch_verified). The §9-§13 re-slice
pool is exhausted. Record:
`docs/audit-history/28Sep2026-sections-11-12-reslice-reconciliation.md`.
Snapshot: HEAD `4201a02` (PR #92 merged 2026-09-27), post-merge main
run `36341230913` success.
Updated 2026-09-28 (erratum + post-merge addendum, PR #93): two claims
in the #93 record corrected — the lineage count is EIGHTH (seven
records preceded it), and the protection read-back ordinal retracted
(clean both-surface read-backs stand; the count does not). Post-merge
main run `36363406997` attempt 1 ended `failure` with ALL 10 required
contexts green — the sole failure was the ADVISORY `benchmark-perf`
job (fail-closed by design): first occurrence in all visible main
history, failing check `cmp_validation.db_operations` (5-sample
ANALYZE DB stage, P1 20ms budget, p95 64.1ms; the P5 100ms budget
passed), rerun-failed-jobs attempt 2 `success` on the same commit —
shared-runner latency jitter, not a regression; R-01 promotion of
benchmark-perf to required requires hardening the stage's sample basis
first. Record §7.
Updated 2026-09-28 morning (FR9 debt-matrix re-slice reconciliation):
the paste presented the OpenAlgo host console (06:42-06:44 IST
rollover/rebuild/login window, attributed host-layer — all five console
signatures are host-checkout emitters with zero LOATS-tree hits) plus
the FR9 report's sections 14 + 13, containment-proven 7/7 and 14/14
against archive lines 227-253; every F9 row already dispositioned
upstream (F9-H-04's closure re-verified live at the wired call site
`orchestrator.py:1856-1857`). The wave's one real finding: R-13's
FIFTH occurrence — 28Sep morning rollover storm 00:43:31-01:14:58Z
(IST 06:13-06:44), 145 OPENED events = 29 cycles x 5 breakers, 1,233
fail-closed refusals, ZERO 404s, zero decisions, self-healed exactly
at the host's 06:44 broker login; recovery forward-scan clean.
Record:
`docs/audit-history/28Sep2026-fr9-debtmatrix-reslice-reconciliation.md`.
Snapshot: HEAD `8384264` (PR #94 merged 2026-09-28).
Updated 2026-09-28 (FR9 production-readiness re-slice reconciliation,
post-PR-#95 main): the paste's §15 Production Readiness Assessment was
containment-proven 14/14 against archive lines 255-271 (first per-claim
verdicts for §15; its §14 repeat collapsed under the debt-matrix
record). Every pasted gate row dispositioned live at this HEAD:
as_of_date call site re-verified (`orchestrator.py:1858`), IV-rank
sentinel two-sided clean, gate-calibration pins live (composite 0.6 /
opposition 0.4), audit chain present (`previous_hash` schema +
head-seed extension), benchmark-perf advisory at `ci.yml:365`,
protection contradicted-live on both surfaces (tenth consecutive clean
read-back); P5 span of record live (quartet green, `ended_at: null` is
in-progress state, earliest valid close 08Oct 08:02Z). The NOT-READY
verdict stands — live capital stays gated on the dated chain (R-01/
R-13/S-14/S-15 30Sep, R-05 01Oct, R-12 08Oct 08:02Z). No new findings:
forward scan clean past the 01:15:58Z recovery cutoff (713 lines, zero
breaker events, no sixth storm; R-13 stays at five occurrences).
Record:
`docs/audit-history/28Sep2026-fr9-prodreadiness-reslice-reconciliation.md`.
Snapshot: HEAD `422b022` (PR #95 merged 2026-09-28).
Updated 2026-09-28 (FR9 re-slice family final-member collapse, post-PR-#96
main): the twelfth family member — router paragraph plus verbatim §15/§14
repeats, NO new section — collapsed as predicted by the #95 and #96 pool
arithmetic: containment-proven 12/12 (§15) and 7/7 (§14) against the
archive; the #96 per-claim §15 verdicts carry over untouched (the code
state is bit-identical at this HEAD — only docs and the ratchet re-pin
landed since). Router paragraph verified claim-by-claim: all REGISTERED,
none new (R-01/S-14/R-13-hardening/R-08/S-15 30Sep, R-05 01Oct, R-12
08Oct 08:02Z); P5 span live (quartet green, earliest valid close 08Oct
08:02Z); protection read-back clean on both surfaces — eleventh
consecutive (the classic REST protection GET 404'd again minutes before
rendering the full config; the untracked UTF-16 junk capture it left was
deleted, never staged); R-13 forward scan from the 01:15:58Z recovery
cutoff clean — 21,750 structured records, zero breaker events, no sixth
storm, count stays at FIVE. The NOT-READY verdict stands; the unre-sliced
pool is UNCHANGED (§1-8, §16-21, Appendix) — this member consumed no new
section. Record:
`docs/audit-history/28Sep2026-fr9-final-member-collapse-reconciliation.md`.
Snapshot: HEAD `3732fe7` (PR #96 merged 2026-09-28), post-merge main run
`36378162598` success.
Updated 2026-09-28 (R-13 sixth-occurrence pin, post-PR-#97 main): the
thirteenth paste-family member's three PS 5.1 failure tails reproduced
live as parse-time artifacts with their intended operations' real
outcomes verified on the remote (PR #97 MERGED 05:56:31Z, `git diff
5ebb3ad origin/main` EMPTY via bash, `protection-live.json` never
tracked in any commit); §15/§14 repeats containment-proven 12/12 and
7/7 against the 15Sep source; router block all-REGISTERED. The wave's
one real finding: R-13's SIXTH occurrence — mid-session
06:44:26-06:46:32Z (12:14 IST Monday, first non-rollover profile),
5 OPENED events = 1 cycle x 5 breakers, 48 fail-closed refusals,
~2-minute self-heal, zero decisions, zero residue (P5 quartet green
through; `unhandled_exceptions: 0`). NOT-READY verdict stands; dated
chain unchanged. Record:
`docs/audit-history/28Sep2026-r13-sixth-occurrence.md`.
Snapshot: HEAD `22b6670` (PR #97 merged 2026-09-28), post-merge main
run `36384520008` success.
Updated 2026-09-28 (second wave: foreign continuation edit reconciled,
R-14 pinned): the uncommitted `17Sep2026-p5-openalgo-auth-outage.md`
Continuation-4/5 sections (edited outside the session at 13:05 IST)
were claimed by the operator and reconciled by live probes — C4
anchors verified (289 decisions DB=log for 2026-09-25, recovery
08:58-08:59Z); C5 observations stand (zero `data/audit.log` rows
26-28Sep despite a live Monday session, routing quartet green,
breaker green) but its mechanism was FALSIFIED: all three configured
RSS feeds fetch in <0.5s from the host (no dead content was ever
served) and the real cause is untimed newspaper4k article downloads
(4.3-26.6s each measured live, up to ~60 per cycle) inside the 8.0s
producer window — once cold-article churn crossed the window at
02:28:22Z (last persist 07:58:22 IST, scores healthy 0.76-0.80 up to
the stop), every sweep is cancelled pre-aggregation and the 15-min
freshness gate starves (368+ min by 14:06 IST, 1,587 alerts, zero
recovery) while transport counters stay green (breaker 8,009/8,009
successful; budget-warning median pinned at 8,003-8,009ms = the
window firing). Opened as R-14 (P2-watch); the fix decision rides the
30Sep window under the ADR-0016 freeze. Record: erratum appended to
`docs/audit-history/17Sep2026-p5-openalgo-auth-outage.md` (28Sep).
Snapshot: HEAD `8c62520` (PR #98 merged 2026-09-28), post-merge main
run `36393072938` success.
Updated 2026-09-28 (FR9 §16 module-table member reconciliation,
post-PR-#99 main): the fifteenth family member re-sliced the archive's
§16 Module-by-Module Review — the FIRST member to consume §16 — plus a
verbatim §15 repeat; containment-proven 15/15 (§16) and 12/12 (§15)
against the 15Sep source. Fresh §16 per-claim verdicts at `e4e110e`:
8 of 14 rows CONFIRMED; 1 PARTIAL (orchestrator's F9-H-04 citation
stale — the wired call site `orchestrator.py:620` passes the snapshot
key into `_execute_cmp_strategy(as_of_date=None)`, whose None-default
resolves the UTC-date-under-IST-offset semantic); 4 rows cite findings
restored/closed upstream (F9-C-01 `insufficient_history` sentinel live
at `rules.py:513`; F9-H-01 0.6/0.4 pins live at `strength.py:115/:130`,
S-03 RESTORED; F9-M-05 2SD live at `strike_selection.py:30-32`, S-06
RESTORED; F9-M-01 `previous_hash` chaining live in database.py); 1
superseded (sentiment "dead in prod" → F9-H-03 closed 20Sep; live
state is the R-14 P2-watch starvation mechanism). The NOT-READY
verdict stands; the unre-sliced pool SHRINKS to §1-8, §17-21,
Appendix. The member also surfaced a SECOND foreign edit — a
"corrections at day close" block on the 17Sep outage doc — kept with
an inline operator annotation (sixth-occurrence count confirmed, not
seventh; R-13/R-14 conflation fixed; full storm span 2m06s, global
breaker 62 s). Record:
`docs/audit-history/28Sep2026-fr9-s16-module-table-reslice-reconciliation.md`.
Snapshot: HEAD `e4e110e` (PR #99 merged 2026-09-28), post-merge main
run `36403612800` success.

| ID | Priority | Category | Status | Due | Next action |
|----|----------|----------|--------|-----|-------------|
| R-01 | P1 | CMP latency decision | CLOSED by ADR-0021 (decision (b)) | — | The user selected (b) at the 2026-09-30 checkpoint: the CMP budget is amended to the measured architecture (1 Hz cadence / 1 s compliance budget; stage budgets TA 80 / DB 20 / round-trip 100 ms unchanged). Evidence cited per ADR-0016 §Decision.2: 0/26,413 + 0/1,278 cycles compliant across the checkpoint spans with every isolated stage meeting its own budget; benchmark-perf green on 15 consecutive main runs. Same wave: `src/loats/latency_budget.py` single enforcement source (7 surfaces re-derived incl. a seventh found by the AST scan — the cycle-loop 100 ms adaptive-sleep floor, contradicted the documented 1 Hz cadence), benchmark-perf renamed `benchmark-perf (F9-H-02 gate)` and promoted to the required-context list, S-14 flipped SUPERSEDED, register net extended in-commit. Option (a) producer decoupling folds into the post-span producer wave (ADR-0016 §4) after 13Oct. Evidence: `docs/adr/0021-cycle-latency-budget-measured-amendment.md` |
| R-02 | P1 | CMP P5 kill-switch span proof | CLOSED by ADR-0018 | — | See the R-02 section below |
| R-03 | P2-watch | Benchmark flake | OPEN — watch | on recurrence | py-spy dump protocol on next hang |
| R-04 | P3 | Accepted residual | ACCEPTED | — | Revisit with the post-checkpoint producer wave |
| R-05 | Ops | Environment, dated | OPEN | 2026-10-13 | Shared-ambient-venv rebuild BLOCKED until the live P5 span closes: the supervisor runs on ambient Python 3.12 (verified 01 Oct: pid 2936 `C:\Program Files\Python312\python.exe scripts\run_p5_forward_test.py --resume`, span 141804, mark 13 Oct 19:48 IST); rebuild per the project recipe in the post-span window and re-run the fresh-venv pip-audit replication (pip-audit==2.10.1 --ignore-vuln PYSEC-2026-3740); repo .venv (py3.12.7) is unaffected and remains the gate interpreter |
| R-06 | Process | Register discipline | CLOSED by this file | — | Maintain per the rules above |
| R-07 | P2 | Test infra: orphaned mutant sweep | CLOSED by the 30Sep window decision (b) | — | Decision (b): pre-run frozen-tree guard. `TestFixerHooksSpareFrozenEvidence._guard_frozen_trees_or_skip_foreign_hold` probes the frozen trees with the sweep's own primitive (`git status --porcelain`) BEFORE the sweep and skips fail-visible on a foreign hold (orphaned mutant sweep / concurrent dirtying process); the shipped-config leg re-checks post-sweep with an exact-banner TOCTOU assertion. RED-proven 30Sep: a pre-dirtied frozen file produces `SKIPPED ... R-07 frozen-tree guard`; clean tree runs the real sweep green. Option (a) process-tree kill rejected: kills the wrong child on shared runners |
| R-08 | P2-ops | Degraded duplicate OpenAlgo instance (shadowed :5000) | CLOSED by the 30Sep window decision (bind-or-exit) | — | LOATS-side half implemented in-repo: `src/loats/preflight.py::check_duplicate_listener` runs FIRST in `TradingSystem.initialize` (before any resource init, so refusal needs no teardown) and refuses the boot when `<openalgo_base_url>/metrics` answers with the LOATS identity marker (`cycle_time_stats`) — a live duplicate; foreign listeners (the healthy host), dead endpoints and timeouts are clear; skipped under ENVIRONMENT=test. Pinned RED-proven in `tests/test_preflight_r08.py` (faked transport; wiring leg proves the guard is the first initialize step). HOST-side half (the asymmetric :5000 bind itself) lives in the OpenAlgo checkout and ships via upstream PR #2047 — the pre-flight makes a relaunched LOATS fail fast against ANY live duplicate regardless |
| R-09 | P2-fixed | Benchmark write-path poisoning (failed INSERTs left open transactions; wall-clock ids collided) | CLOSED by `fix/benchmark-txn-hygiene` | — | Same-commit runs at `ba4febd` graded 8/10 PARTIAL (12:59) and 12/12 PASS (13:13): root cause was nondeterministic lock cascade (30 s busy_timeout starvation), not a budget regression. Fixed: `_rollback_on_error` on 15 sync writers, pool-release transaction repair, uuid4 benchmark ids; `tests/test_transaction_hygiene.py` pins it |
| R-10 | P2-fixed | Benchmark gate false-green: sample success rate ungraded; focused signal fixture rejected at insert | CLOSED by `fix/perf-gate-success-rate` | — | Found by the post-merge verification run at `879015c`: the F9-L-03 guard rejected 100/100 `signal_round_trip` samples (fixture lacked the `test` provenance tag) while the gate graded green off the exceptions' durations. Fixed: `validate_cmp_latency_gates` now grades the sample success rate (incl. the stage-gate composition) fail-closed, and the fixture carries `metadata["test"]`; pinned in `tests/test_performance_analyzer.py::TestSuccessRateGate` |
| R-11 | P2-fixed | Stage gates graded a single-sample population (n=1 TA spike graded 26Sep 9/10 PARTIAL; same class 09/17/20Sep) | CLOSED by `fix/benchmark-stage-samples` | — | Under-sampled STAGE gates fail closed (`insufficient_samples`); round-trip harness discards one warm-up call and measures 5 samples/stage, medians reported; pinned in `tests/test_performance_analyzer.py::TestStageGateSamplePopulation` |
| R-12 | P3-watch | P5 decisional-leg evidence: the graded stream read zero routed attempts because every cross-process resume DISCARDED prior generations' counters (`max(live−logged,0)` floor in the supervisor resume path); the span's true population is 395 audited attempts (106 on 24Sep + 289 on 25Sep), DB-corroborated | OPEN — instrument defect root-caused and fixed (`fix/p5-resume-counter-carry`); span disposition rides the LIVE span (graded at the 13Oct mark) | 2026-10-13 | The superseded 080208 clock (earliest close 08Oct 08:02Z) was replaced by watchdog succession: grade the LIVE span `p5_forward_test_20260929_141804.json` (started_at 2026-09-29T14:18:04Z, 14-day mark 13 Oct 19:48:04 IST); its `counters_baseline` already carries 108 routed decisions from the closed predecessor generations. An attempt must be carried or fired before `ended_at`, else the run grades FAIL-closed on the decisional criterion by design. The "candidates rejected every time" reading was one-sided: the same 25Sep log window holds 110 rejections AND 289 routed successes (all `success` outcomes, statuses PENDING in `trade_decisions`). 30Sep options: seed-carry the corroborated totals into the graded stream (supervisor provenance event) vs successor span vs record the FAIL-closed evidence. Evidence: `27Sep2026-p5-resume-counter-carry-reconciliation.md` |
| R-13 | P3-watch | Host maintenance/absence windows drove LOATS's breaker storms — SIX occurrences 25-28Sep, every one fail-closed and self-healed: Fri 25Sep ~10:56-14:12 IST (host-absent, ~14.8k breaker-open refusals across two rotated logs); Sat 26Sep 06:30-08:30 IST (rollover, ~4.3k); Sun 27Sep morning 06:46-06:58 IST (documented window: global OPEN, 351 refusals, 35 per-source cycles, 102 fallback-expiry 404s); Sun 27Sep EVENING 19:38-20:31 IST (85 OPENED events = 17 cycles x 5 breakers, 3,373 refusals, ZERO 404s — expiry-cache state differed, noise profile is not fixed; the 19:55 host restart landed mid-storm); Mon 28Sep morning 06:13-06:44 IST (145 OPENED events = 29 cycles x 5 breakers, 1,233 refusals, ZERO 404s, zero decisions, self-healed at the host's 06:44 broker login + master-contract rebuild completion); Mon 28Sep MIDDAY 12:14 IST (06:44:26-06:46:32Z, mid-session regular hours — first non-rollover occurrence: 5 OPENED events = 1 cycle x 5 breakers, 48 refusals, ZERO 404s, zero decisions, ~2-min self-heal) | CLOSED — accept-as-designed (30Sep window decision (c)) | — | The user accepted the class as designed at the 30Sep window: every occurrence (six on record, one mid-session) failed closed and self-healed with zero bad orders — the evidence stand is the protection, and NO code change ships mid-span (gen14 grades to 13Oct). Rollover grace (option (a)) was ruled insufficient by the register (occurrences hit mid-session); rebuild-aware readiness probe (option (b)) touches the live order-path error surface mid-span and is DEFERRED to the post-span producer wave, where it re-enters as a candidate alongside the option-(a) producer decoupling. Fail-closed audit evidence stands as the permanent record; ADR-0016 freeze expiry handled by ADR-0021 does not reopen this |
| R-14 | P2-watch | Sentiment producer starvation via untimed article downloads: `parse_rss_feed` extracts up to ~60 article pages per sweep with newspaper4k (`Article.download()`, no timeout, sequential) inside the 8.0s producer window; measured live 28Sep: 4.3-5.7s economictimes, 16.6-26.6s moneycontrol, 5.9-19.3s livemint per article. Once cold-article churn pushed sweep cost past the window (28Sep 02:28:22Z = 07:58:22 IST, last persist; scores healthy 0.76-0.80, news_count 55, degraded=0 up to the stop), the window cancelled EVERY sweep — budget-warning median pinned 8,003-8,009ms from 03Z, zero persists thereafter, the 15-min freshness gate starved to 368+ min by 14:06 IST (1,587 alerts, zero recovery), zero audit rows on the day, while transport counters stayed green by design (breaker 8,009/8,009 successful — breakers count only raised exceptions; feeds themselves fetch <0.5s) | VERIFIED 29Sep evening (same day as fix): gen11 soft-stopped and the watchdog fresh-started gen12 on the #109 code (editable install verified first — `.pth -> src`); like-for-like evening windows 13:40-14:10Z — over-window rate 37% (28Sep) / 42% (29Sep) pre-fix -> 14% post-fix, ALL cold-start (first 214s), then ZERO over-window events from 13:52:06Z through end of generation (pins-only, cancellation enforcing); max 12.7s -> 9.9s = the DESIGNED worst case (7s per-feed budget + 3s fetch tail, window-cancelled at 8s with partial retention, docstring `sentiment.py:217-222`); persist truth 380 rows >=13:48Z, freshest 13:58:25Z — persist DURING the warning window proves partial retention. 24Sep span closed gracefully 13:45:49Z (11 generations, kill-switch PASS each); NEW span `p5_forward_test_20260929_134805.json` started 13:48:05Z — the 14-day accumulation clock RESETS, grade the new span (R-12 close arithmetic moves accordingly). 30Sep REGULAR-hours CONFIRMATION PROBED 05:13-05:15Z (10:43-10:45 IST, market open): sentiment persist truth 1,017 rows/90min, freshest 2.8 min; audit 985 rows/24h, latest live; freshness-gate alerts today ZERO (28Sep signature: 1,587, zero recovery) — the starvation class is NOT present under regular hours; over-window sweeps (6.7-9.6 s) persist via partial retention as designed. gen14 live process still runs pre-wave code (mid-span, by design — R-16); the 80 ms S-14 threshold lands at the next generation pickup. Evidence: `29Sep2026-f9m01r2-chain-reanchor-and-backup-fidelity.md` §1-2 | 2026-09-30 | Standing confirmation DISCHARGED 30Sep regular hours. Fix shape (i)-(iv) shipped in #109; keep the watch row open through gen14 close (13Oct) for any recurrence |
| R-15 | P1-fixed | F9-M-01-R2: `scripts/repair_f9m01_chain_head.py` serialized the ALREADY re-anchored entry list to `*.f9m01r1-backup` (`main()` ran `reanchor_span` before `write_repaired_log`; c588be7 original) — the "backup" held repaired content, zero broken links, and could neither restore nor re-derive the pre-repair state. Fired on BOTH real runs (24Sep, 29Sep); docstring claim false for the JSONL leg (the SQLite DB snapshot was genuine both times — taken before `repair_db`). No production trail corrupted: the live chain was repaired correctly both times; only the restore artifact was degraded | FIXED same session (F9-M-01-R2): backup serialized from the PRE-repair list before mutation; repair-record reason now reports actual run/link counts (was a hardcoded "23 frozen runs" — false for the 1-run 29Sep repair); pinned by `tests/test_repair_backup_fidelity.py` (4 tests; RED proven against c588be7 before the fix). 24Sep-era JSONL/DB backups preserved under `*.20260924-preserved` before the 29Sep apply overwrote the fixed names. Evidence: `29Sep2026-f9m01r2-chain-reanchor-and-backup-fidelity.md` §3-4 | — | A future restore rehearsal (30Sep+ ops window) may validate the preserved backups end-to-end; NOT urgent — the DB backups are genuine and pre-repair state is reconstructible from them |
| R-16 | P2-watch | Span governance: a HEALTHY P5 supervisor never picks up merged code (the watchdog is revive-only; LOATS_P5_Resume is disabled), and a graceful soft-stop CLOSES the running span (fresh span, day-0 reset of the 14d accumulation clock). The 13:37 IST paste assumed a scheduled restart task would deliver #109 to the runtime — false at probe time; the verification required the supervised soft-stop path executed manually | OPEN — mechanism understood and recorded; no code change pending. The 29Sep verification session itself is the worked example (gen11 soft-stop → gen12 verification → gen13 fresh span). Succession continued past the 134805 span (whose 13Oct 13:48Z close arithmetic rode a superseded clock): the LIVE span is `p5_forward_test_20260929_141804.json` (started_at 2026-09-29T14:18:04Z) → earliest valid close 13 Oct 19:48:04 IST | 2026-10-13 | If the wave roadmap requires a mid-span code pickup again, soft-stop is the only delivery path and resets the clock — schedule verification sessions at span boundaries where possible. Evidence: `29Sep2026-f9m01r2-chain-reanchor-and-backup-fidelity.md` §2, §5 |
| R-17 | P2-watch | Kill-switch live defect: `/kill` failed twice 30Sep (15:47:42Z, 15:53:24Z, `Failed activate kill switch: string indices must be integers, not 'str'`) — `activate_kill_switch` iterated the orderbook envelope's KEYS as order rows; the wire contract (gateway `services/orderbook_service.py`, live AND sandbox paths) returns `data` as `{"orders": [...], "statistics": {...}}` with broker vocabulary `orderid`/`order_status` lowercased ("open", "trigger pending"). CI never caught it: every existing kill-switch test fed canonical flat fixtures (consumer vocabulary, not wire vocabulary) | FIXED on main and VERIFIED LIVE 01Oct: #114 merged 06:10:48 IST (`3b93fe5`); the running process picked the fix up WITHOUT a span close (watchdog revive, `restarts: 3`, editable `.pth -> src`) — the 14-day clock stayed on gen14's `started_at 2026-09-29T14:18:04Z`, valid close unchanged 13Oct 14:18Z. First drill attempt 13:14 IST correctly REFUSED activation (`Failed fetch orders kill switch, rolled back` — broker session dead, kill switch must reach the broker to cancel orders: fail-closed rollback semantics proven). Re-drill 13:33 IST PASSED on all legs: activation 08:03:04.842Z, 122 consecutive orchestrator-blocked cycles 08:03:09-08:05:11Z (enforcement), deactivation 08:05:12.057Z, `kill_switch_verified: true`, `unhandled_exceptions: 0`, zero TypeErrors post-merge | — | CLOSED 01Oct — live leg satisfied inside the span; the 13Oct kill-switch span-attachment requirement is now evidence-backed. R-12 routed-decision reconciliation remains the sole open span-close item (due 13Oct) |
| R-18 | P2-docs | Compliance posture carried bulk assertions ("SEBI: Full compliance", "NIST 800-53", "ISO 27001:2022") with no applicability assessment — external review 02Oct: tool scans, logging, and a self-imposed rate cap do not establish SEBI/NIST/ISO compliance; the 10-OPS figure alone is not a compliance finding | CLOSED by `docs/COMPLIANCE-MATRIX.md` (02Oct compliance-evidence wave) | — | Applicability assessment first: LOATS is paper-trading/report-only (no live order path), so the SEBI/NSE Feb-2025 client obligations (registration above TOPS 10 OPS, static IP, unique client API keys, algo-ID tagging) are operator/broker-owned and open until live trading is enabled; in-repo controls (`max_ops=3` limiter + HC-14 net, kill switch with the 01Oct live drill, SHA-256-chained audit, Decimal risk limits) are evidenced from the paper path only; NIST/ISO scoped explicitly (no ATO, no ISMS, no certification). README/docs-README bullets re-pointed at the matrix. Sources read: SEBI circular 0000013 (04Feb2025) + NSE INVG/67858 (05May2025) |

Updated 2026-09-30 (08:05 IST, collapse #17 — first member of the new
day; §19/§20 pool section consumed): the 02:15 IST 30Sep composer-paste
member (tenth consecutive collapse, created AFTER the #111 merge landed
at 16:45:47Z 29Sep) carries three blocks. (1) An OpenAlgo HOST-log
transcript 07:35:56-07:37:34 IST: startup errors on the stale broker
token (`Incorrect api_key or access_token` in quotes/funds), the
07:36:41 user re-login redirecting to /broker, the 07:37:12 broker
callback, master-contract rebuild (107,756 records, 17s), WS/order-adapter
connect and catch-up recovery — the arc completes INSIDE the paste
(self-healed re-login); every emitter is host-checkout (`G:/.OA/OpenAlgo`):
the pinned set (strategy_module_db, order_update_service, order_adapter,
auth, brlogin, auth_db, auth_utils, master_contract_db) plus TWO newly
pinned: `master_contract_cache_hook` -> host
`database/master_contract_cache_hook.py`, `catch_up_processor` -> host
`sandbox/catch_up_processor.py`. Zero LOATS-source lines; no post-relogin
recurrence of the token signature inside the transcript (host `logs/`
holds no 30Sep rotation, so the transcript itself is the evidence).
(2) Two PS 5.1 tails, both parse-death class (`The '<' operator is
reserved for future use` on literal `<abs-path>` and `<snapshot>
<outdir>` template tokens) — NOTHING executed; intended operations
verified live at record time: PR #111 MERGED 2026-09-29T16:45:47Z,
merge commit ee47948 = local main HEAD, branch purged remote AND local
(ls-remote empty); protection GET field-by-field green TODAY
(approving=1, dismiss_stale=true, code_owner=false, last_push=false,
strict=true, 10 contexts, enforce_admins=true, restrictions=null) —
the derive recipe's 4-flag patch contract intact. The same PS session
left the pinned junk signature at repo root: UTF-16LE `verify.json`
holding a GitHub 404 JSON body (PS-redirect capture, never committed);
deleted untracked — tree clean, ceiling stays 506. (3) A
standing-risks queue plus a §19 Executive Summary / §20 Architecture
Overview re-slice: containment 37/160 normalized lines inside the
15Sep FR9 SOURCE archive (7/8 distinctive-phrase greps verbatim; miss
= phrasing drift `saturated at 100.0`), 0/160 against the #16 record —
a verbatim re-slice of the SOURCE sections, not of the member-16
mirror, so §19/§20 join the consumed pool; every §19 finding remains a
dispositioned register row (S-02/S-03/S-13 RESTORED; `previous_hash`
link chain present; `src/loats` 40 .py files vs the pasted `38`) and
§20's live claims carry over. Freshness delta, not a contradiction:
the member's queue says R-13 `six occurrences` — the register (29Sep
morning update) pins SEVEN (08:45-08:55 IST pre-open storm); all five
queue rows otherwise matched register rows (R-14 standing confirmation,
gen14 Telegram exercise, R-05 01Oct, R-12 13Oct, R-15 optional
rehearsal). NEW LIVE FACTS at record time: gen14 quartet green
(`p5_forward_test_20260929_141804.json`, mtime 0.3 min,
`started_at 2026-09-29T14:18:04.991Z` unchanged, `ended_at:null`,
`restarts:1` — up from 0 at the #16 record, i.e. ONE supervisor
restart/resume event between 29Sep 21:50 IST and this probe; the span
was NOT closed and re-started, so the 14-day clock is UNCHANGED —
earliest valid close 2026-10-13 14:18Z; `kill_switch_verified:true`,
`unhandled_exceptions:0`, `last_sampled_at 02:18:53Z` within sampler
cadence of the probe). Zero fresh findings; register-append-only wave.

Updated 2026-09-29 (21:50 IST, collapse #16 — full re-slice of the FR9
source; fifteenth record delivered with it): the 21:36 IST composer-paste
member (ninth 29Sep member, created AFTER the fifteenth record was
written at 21:22 IST) re-slices the ALREADY-DISPOSITIONED 15Sep FR9
forensic source verbatim — containment 37/38 lines inside
`docs/audit-history/15Sep2026-FR9-forensic-review-report.md`
(§20 Architecture Overview + §19 Executive Summary + wave-deltas line);
the sole novel line is the session footer. §20's live claims verified
against the tree at record time: routing flag default OFF
(`analyzer_routing_enabled: False`), ANALYZE default mode, producer
window 8.0 s, lot 25, CMP 0.6/0.4 gates restored (S-03), VIX symmetric
fail-safe, P5 scripts under their real names (`run_p5_forward_test.py`,
`verify_p5_forward_test.py`, `fr7_health_check.py`,
`check_per_module_coverage.py`, `benchmark_performance.py`);
`src/loats` now holds 40 .py files — the pasted "38 files" figure
predates the #109/#110 wave. Every §19 finding (IV-rank saturation,
threshold drift, sentiment dead, `as_of_date`, self-hash chain,
cycle-latency gate, P5 invalid evidence) is a dispositioned register
row — S-02/S-03/S-13 all RESTORED (`previous_hash` link chain present
in `database.py`; the pasted "self-hash only" verdict is stale) — zero
fresh findings. NEW LIVE FACT: gen14 quartet green at record time
(snapshot mtime 0.5 min, `last_sampled_at` 16:19:39Z,
`kill_switch_verified:true`, `unhandled_exceptions:0`, `restarts:0`,
`ended_at:null` = in-progress by design); R-12/R-16 arithmetic
unchanged (gen14 `started_at` 14:18:04.991Z → earliest valid span close
2026-10-13 14:18Z; the mid-span real Telegram exercise remains
outstanding in the 30Sep window). LANDING GAP DISCHARGED: the fifteenth
record (`27c0ee0`) was still unpushed at member-16 receipt (GitHub 422
on the SHA — never landed); this register wave delivers BOTH records on
one branch. Ceiling stays 506, tree clean; register-append-only wave.

Updated 2026-09-29 (21:20 IST, collapse #15 — post-#110 member; SPAN
ARITHMETIC MOVES TO GEN14): the 21:10 IST composer-paste member (eighth
29Sep member, created AFTER the #110 merge landed at 20:42 IST) is the
day's fifteenth collapse. PS-5.1-tail half: the parse-death
(`The '<' operator is reserved for future use`) of the exact
`gh pr create` line for #110 — a literal `<pr-body.md>` token
transcribed from the report template dies at PARSE time, so NOTHING in
that line executed; the intended operation verified live instead: PR
#110 MERGED 15:12:37Z (F9-M-01-R2 backup fidelity; c5f118f fix,
7b61eab register, 30eb72e tests), branch purged (ls-remote empty),
local main at 185a982 with a clean tree. Prose half: containment 19/35
lines inside the 15Sep FR9 source archive (§19 verdict + STEP-1-4
roadmap re-slices), 0 novel finding lines; the standing-risks queue
matched register rows row by row (R-12 13Oct arithmetic, 30Sep
discharge list R-01/S-14/S-15/R-08/R-13, R-05 01Oct, R-15 optional
restore rehearsal, gen13 cold-start watch) — register-sourced, zero
fresh findings. The member's file-mutation-verifier warning is
discharged: the refused scratch write (fix_register.py) was a repair
script for a TRANSIENTLY mangled working-tree register draft (doubled
`||` pipes, R-15 fused into the R-13 row, orphaned R-14 tail); the
damage is ABSENT at HEAD — 16 single-pipe risk rows, zero `||` lines,
no orphaned tail — and the post-merge 185a982 CI read 16 contexts
green (Docker Build skipped by design). NEW LIVE FACT superseding the
member's watch line: gen13 (`..._134805.json`) closed gracefully at
14:11:43.942Z (294 cycles, 0 unhandled exceptions) and the watchdog
fresh-started gen14 (`p5_forward_test_20260929_141804.json`,
restarts=0, a fresh span, not a resume) at 14:18:04.991Z — LIVE and
green at record time (snapshot mtime 0.28 min, `last_sampled_at`
15:47:12Z, `kill_switch_verified:true`, `unhandled_exceptions:0`,
`ended_at:null` = in-progress by design). R-12/R-16 close arithmetic
MOVES AGAIN: the 14-day accumulation clock anchors to gen14
`started_at 2026-09-29T14:18:04.991Z` → earliest valid span close
2026-10-13 14:18Z; the real Telegram /kill→/resume exercise must land
mid-span (30Sep ops window) or the span grades fail-closed. Ceiling
stays 506, tree clean; register-append-only wave.

Updated 2026-09-29 (EVENING — R-14 VERIFIED live; F9-M-01-R2 chain
re-anchor; R-15 opened and fixed): gen11 (pre-#109 code in memory) was
soft-stopped via the supervised path and gen12 verified the fix LIVE —
over-window maxima GONE in steady state (zero events 13:52-14:11Z; the
10 residual events were all cold-start, first 214 s, max 9.9 s = the
designed 7 s budget + 3 s fetch-tail ceiling under the 8 s window
cancel), persist truth 380 rows during the warning window. The graceful
stop CLOSED the 24Sep span (11 generations, kill-switch PASS each); a
NEW span started 13:48:05Z — the 14-day clock RESETS (R-12 close
arithmetic -> 13Oct 13:48Z; R-16 records the governance lesson). The
gen13 boot then surfaced the 25Sep frozen-writer chain damage (first
seen 25SepT21:30Z, static for 4+ days): 398 broken links, ONE writer
lifetime, window 25Sep 09:00:33-09:59:56 IST, interleaved with 270
correctly-linked entries from a sibling writer. Re-anchored 29Sep
evening under the full 24Sep protocol (writer stopped, watchdog
disabled, rate-check dry-runs, apply, tool+independent+production
verification, fresh-append head-advance proof): 668 entries re-anchored,
668/668 DB rows mirrored, 0 orphans, all three verifiers PASS. The apply
EXPOSED R-15 (both real JSONL backups held repaired content — the tool
mutated before snapshotting); fixed and pinned same session
(F9-M-01-R2, tests/test_repair_backup_fidelity.py, RED-then-GREEN);
24Sep-era backups preserved under *.20260924-preserved. Evidence:
docs/audit-history/29Sep2026-f9m01r2-chain-reanchor-and-backup-fidelity.md.

Updated 2026-09-29 (30Sep ops window — R-14 fix shape implemented;
Telegram "bot not functioning" verdict): R-14 implemented as shape
(i)+(iv) — layered bounds inside the thread leg
(`src/loats/sentiment.py`: `ARTICLE_EXTRACT_SOCKET_TIMEOUT_SECONDS=6`,
`ARTICLE_EXTRACT_WAIT_SECONDS=3` async wait bound with skip,
`ARTICLE_EXTRACT_CONCURRENCY=4` global semaphore,
`FEED_FETCH_TIMEOUT_SECONDS=3`, `FEED_SWEEP_BUDGET_SECONDS=7` with
partial retention, failure negative-cache TTL 120 s) plus (iv)
sustained-starvation escalation now DELIVERS via Telegram
(`_check_sentiment_liveness` dispatches once per episode, recovery
re-arms, failed dispatch retries loudly — 29Sep had 49 log-only
warnings, zero delivered). Pinned by
`tests/test_r14_bounds_and_liveness_alert.py` (15 tests). Telegram
credentials verified HEALTHY live (getMe ok, sendMessage delivered
message_id 950, no webhook, no 409-holder other than the in-process
poller — the two 10:53-10:54Z Conflict lines were probe-collisions
with the live poller); the operator-visible failure decomposes into
the log-only liveness alert class (fixed) and the DEBUG-silent
suppression class (now WARNING-observable; polling task got a
dead-man switch that logs a dead poller and re-arms `start()`).
Live-process evidence at decision time: 23,945 budget warnings,
maxima 41.6 s, 428/457 minutes over-window; 270 `audit_log`
REJECT rows (prudence stream alive); `trade_decisions` last row
25Sep 09:59Z. ADR-0016 freeze: no behavior change outside the
producer bound and the alert path; hot-loop budget untouched.

Updated 2026-09-28 (FR9 sixteenth paste member collapse, post-PR-#100
main): the sixteenth family member is a fresh composition (consecutive-
paste diff vs the 07:50 member: disjoint) of five PS 5.1 failure tails
whose inline comments cite the s16 wave's OWN commands and SHAs (ratchet
index check, `d0bfaf0`, the sep28-s16-module-table PR create, the
GraphQL protection read-back, `git diff 54e5306 origin/main`), a 9-row
risk table, and a verbatim §16 + §15 re-slice. Timestamp arithmetic: the
paste (12:04 IST) predates the #100 merge (11:19:38Z = 16:49 IST) —
mid-wave transcripts of operations since completed. Parse-death class:
nothing in any tail executed; every intended operation re-proved green
live (ceiling 500 blob+import+ls-files; `d0bfaf0` subject match; PR #100
merged and branch purged; protection approving=1/dismiss_stale/
enforce_admins/strict/10-contexts; `54e5306..origin/main` EMPTY with
`37d9ad7^2 == 54e5306`). Risk table verified CONSISTENT row-by-row,
incl. the kill-switch exercise still outstanding (rotation-mapped log
scan: zero kill events in-span; snapshot `kill_switch_verified` is
STATE, not the exercise) and the R-12 08Oct 08:02Z close (span
started_at + 14d). Containment 15/15 (§16, lines 273-290) + 12/12 (§15,
lines 255-271) against the 15Sep source; §16 identical to the
#100-dispositioned slice, §15 carries #96. Post-merge main at the merge
SHA: 16/16 check runs, 15 success + 1 by-design skip (Docker Build);
`gh run list` stale-page pitfall hit twice in one session — check-runs
API bypass pinned. Zero new findings. NOT-READY verdict stands;
unre-sliced pool UNCHANGED (§1-8, §17-21, Appendix). Record:
`docs/audit-history/28Sep2026-fr9-sixteenth-member-collapse-reconciliation.md`.
Snapshot: HEAD `37d9ad7` (PR #100 merged 2026-09-28), post-merge main
check-runs 15 success + 1 skipped at the merge SHA.

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

## R-13 [P3-watch] Host rollover/rebuild windows drove LOATS's breaker storms (recurring)

Category: ops resilience / host-coupling watch. Status: OPEN — watch
item, RECURRING signature (six occurrences 25-28Sep), every
occurrence fail-closed and self-healed; hardening decision rides the
2026-09-30 ops window (ADR-0016 mid-span freeze binds until the
checkpoint). Confidence: Certain (log forensics at HEAD `10d410f` for
the documented Sunday window; PR #90 rotated-log forensics for the
Fri/Sat predecessors; night-wave log forensics at HEAD `a2991c2` for
the Sunday-evening occurrence).

Evidence (2026-09-27, all times UTC in `logs/loats.log`; IST = Z+5:30):
the OpenAlgo host performed its daily session rollover at 06:46:04 IST
(stored broker session stale, quotes/margin auth failures) and its daily
master-contract rebuild at 06:47:13-06:47:54 IST (Symtoken table
deleted 06:47:17, 109,485-row bulk insert completed 06:47:47, memory
cache loaded 06:47:54). During the combined window LOATS experienced:

- 01:16:44Z first error; global breaker `openalgo` OPEN — tripped by
  the rollover auth gap BEFORE the host's 06:47:13 fresh login;
- 351 `Failed to get quotes: global circuit breaker open` refusals
  (01:16:45-01:21:16Z) — the fail-closed design refusing every
  market-data fetch while the broker token was invalid;
- 35 per-source breaker OPENED events (ta, volatility, price_action,
  options_flow) cycling OPEN -> HALF_OPEN -> CLOSED as the instrument
  registry emptied and refilled;
- 102 `404 No strikes found for NIFTY expiring 04OCT26` errors
  (01:18:59-01:27:18Z): with `/expiry` unresolvable through the
  window, the computed fallback hint `_option_chain_expiry_date(7)`
  (`openalgo.py:250-262`; fallback selection `:301-309`) emitted
  2026-09-27+7d = 04OCT26 — a Sunday, not a listed NIFTY weekly
  (real expiry Tue 29Sep) — a guaranteed 404 per chain fetch from the
  breaker-guarded orchestrator leg (`orchestrator.py:378-411`). The
  404 tail persisted ~9 minutes past rebuild completion because every
  failed `/expiry` kept re-emitting the hint until the global breaker
  closed; the resolved-expiry cache (`openalgo.py:1195-1200`) stores
  on success only, by design.

Outcome: full recovery — final `CLOSED after recovery` 01:28:40Z, ZERO
breaker events after 01:29Z; the decisional funnel produced zero
outcomes (grep-verified), no fabricated data entered any store, and
the live P5 span carries no residue (`unhandled_exceptions: 0`,
1494 cycles at probe time). This is the designed fail-closed behavior
operating correctly through a host maintenance window, not a defect.

Why watch, not close: RECURRING, not single-occurrence — the same
fail-closed storm signature preceded the documented Sunday window at
least three times: Fri 25Sep ~10:56-14:12 IST (host-absent window;
~14.8k `Circuit breaker 'openalgo' is open` cycle errors across
`logs/loats.log.5` + `.log.4`, plus ~4.8k no-historical-data), Sat
26Sep 06:30-08:30 IST (the daily ~06:30 IST rollover; 326 + 2234 +
2045 errors across the 22Z-02Z buckets of `logs/loats.log.2`), and
Sun 27Sep EVENING 19:38-20:31 IST (14:08:49-15:00:50Z; 85 OPENED
events = 17 full cycles x 5 breakers, 3,373 fail-closed refusals,
ZERO fallback-expiry 404s — unlike the morning window's 102: the
expiry-cache state differed, so the storm's noise profile is not
fixed; the 19:55 IST host restart visible in the night console paste
landed MID-STORM, ~17 minutes after onset — consequence/recovery
attempt, not cause; positive control: the sentiment source served
5,767/5,767 calls with zero rejections through the window, its
cache-only path immune by design; P5 snapshot at 23:24 IST:
`unhandled_exceptions: 0`, zero routing decisions in the window).
Every occurrence: fail-closed held, zero decisions, self-healed,
zero audit residue. The 404 burst is
loud-but-expected synthetic-cycle noise that a production operator
would need to triage against real incidents. Hardening candidates
(30Sep, alongside R-08): (a) rollover-window synthetic-cycle grace —
suppress/skip scheduler cycles across the known daily rollover +
rebuild window instead of cycling into a closed breaker; (b)
rebuild-aware readiness probe — gate chain fetches on a host
instrument-registry readiness signal instead of burning the fallback
hint; (c) accept-as-designed — the fail-closed evidence (this record)
stands, no change. Decision owner: the 30Sep ops-review window.
Incident record: `docs/audit-history/27Sep2026-openalgo-rollover-
rebuild-breaker-window.md`; recurrence forensics:
`27Sep2026-p5-resume-counter-carry-reconciliation.md` §3 and
`27Sep2026-fr9-riskmatrix-reslice-reconciliation.md` §4. Section
snapshots: HEAD `10d410f` (PR #88 merged 2026-09-26), CI run
`36263835750` green; row truth-up PR #90 (`2990240`); section sync PR
#91 wave; evening occurrence truth-up at HEAD `a2991c2` (PR #91
merged 2026-09-27).

Fifth occurrence (2026-09-28 morning, structured-log forensics at HEAD
`8384264`; json-parse-first scan, all times UTC in `logs/loats.log`,
IST = Z+5:30): storm span 00:43:31Z->01:14:58Z (IST 06:13-06:44).
Counts: 145 per-source OPENED events (= 29 full cycles x 5 breakers),
1,233 `Failed to get quotes: global circuit breaker open` fail-closed
refusals, 5 CLOSED-after-recovery events (01:14:42-01:14:58Z), ZERO
fallback-expiry 404s — the 27Sep evening's zero-404 noise class again.
Decisional funnel: zero decisions in-window (the single probe-pattern
match, `Enabled Analyzer routing` at 00:43:26Z, is a lifecycle line
whose LOGGER NAME matched, five seconds before onset). Forward scan
after the 01:15Z cutoff: zero breaker hits — positive recovery
evidence. Correlation: onset precedes the paste console's first line
(06:42:32 IST = 01:12:32Z); recovery aligns exactly with the host's
06:44:04 IST broker login + master-contract rebuild completion
(109,485 symbols, console paste). P5 quartet at probe: snapshot mtime
07:05 IST, `last_sampled_at` 01:35:23Z, `kill_switch_verified: true`,
`unhandled_exceptions: 0`; `ended_at: null` correct in-progress state.
The daily-rollover correlation class now holds three mornings running
(26Sep, 27Sep, 28Sep); hardening decision unchanged, 30Sep ops window
alongside R-08; ADR-0016 freeze binds. Evidence:
`28Sep2026-fr9-debtmatrix-reslice-reconciliation.md` §3. Section
snapshot: HEAD `8384264` (PR #94 merged 2026-09-28; this truth-up
rides the PR #95 wave).

Sixth occurrence (2026-09-28 midday, structured-log forensics at HEAD
`22b6670`; json-parse-first scan, all times UTC in `logs/loats.log`,
IST = Z+5:30): storm span 06:44:26Z->06:46:32Z (IST 12:14-12:16),
REGULAR Monday session. Counts: 5 OPENED events (= 1 cycle x 5
breakers: global `openalgo` 06:44:26.495Z, then
`source:ta`/`source:volatility`/`source:price_action`/
`source:options_flow` 06:44:32-06:44:33Z), 48 `global circuit breaker
open` fail-closed refusals, 5 CLOSED-after-recovery events
(06:45:28.914-06:46:32.308Z, ~2 minutes — smallest storm of the six),
ZERO fallback-expiry 404s, zero decisions. Onset trigger: three
consecutive host API HTTP 500 `Server disconnected` failures within
one second (quotes / LTP for NIFTY / historical data), each on its
first retry — no rollover, restart, or rebuild context; the FIRST
mid-session occurrence, so the rollover-window grace option (a) would
NOT have covered it (options (b)/(c) survive for 30Sep). Forward scan
after 06:46:33Z: 905 records through 07:04:42Z, zero breaker mentions.
Telegram alert fired in-window. P5 residue: none
(`unhandled_exceptions: 0`, quartet green, `ended_at: null`
in-progress). Evidence: `28Sep2026-r13-sixth-occurrence.md`. Section
snapshot: HEAD `22b6670` (PR #97 merged 2026-09-28; this truth-up
rides the next protected-main wave).

Updated 2026-09-28 (evening, seventeenth FR9 paste-family member, branch
`docs/sep28-s17-sixteenth-collapse`): the member's STEP-0 F9-M-02 block
was re-executed as the standing R1 drill, not taken as open work —
protection read back contract-exact with ZERO divergences (field-by-field
REST-GET diff vs the pinned contract: the exact 10 contexts, strict, 1
approving review, dismiss-stale, code-owner false, admin-enforced,
restrictions null, force-push/deletions denied); the enforcement probe
rejected a worktree-free commit-tree probe pushed at `main` (GH006, "10
of 10 required status checks are expected"), `origin/main` unchanged
(`37d9ad7`); and ALL THREE verification surfaces resolved for the first
time since the 24Sep migration (GraphQL BPR + classic REST GET 200 — the
24Sep persistent-404 and 25Sep GraphQL-absent quirks have HEALED — +
`protected:true`). SIXTH consecutive clean since the F9-M-02-R1
restoration. GET JSON retained out-of-tree per R1 (session scratch,
sha256 `27eb7756…d2b656e`); ceiling 501 unchanged. §17 per-claim
verdicts: every row CONFIRMED live (ADR-0003/0004 records present; no
`ta`/`py_vollib` pins or imports; zero npm artifacts; deps-sync and
pip-audit required contexts green at the #100 merge; ANALYZE default;
3-feed RSS list; INDIAVIX; telegram) — the external-integrations 🟡
annotation is STALE (F9-M-03 resolved 18Sep by ADR-006 Amendment 7 /
PR #56). Containment: STEP-0 3/3, §17 7/8, §16 15/16 — every miss is a
`##`-heading scaffold (source L273/292/303). Pool after this member:
§1-8, §19-21, Appendix and the §18 steps beyond STEP-0 remain
unre-sliced. Evidence:
`28Sep2026-fr9-sixteenth-member-collapse-reconciliation.md` §7-8.
Snapshot: branch state at `bcbc277` + this wave.

Updated 2026-09-28 (night, F9-M-02-R2): the PR #101 relax → merge →
restore sequence exposed a RESTORE-PUT semantics drift — the server now
RESETS omitted review flags to false, so the 24Sep/R1-era restore body
(count-only `required_pull_request_reviews`) silently applied
`dismiss_stale_reviews:false` (PUT 2xx; caught by the GraphQL read-back,
not the exit code). Corrected minutes later with an explicit-boolean
re-PUT; authoritative read-back 10/10 PASS, zero divergences, both
surfaces agree (`dismissesStaleReviews:true`, count 1,
admin-enforced, the 10 contexts, strict). Exposure window: minutes,
inside the merge session, no pushes by any actor; only stale-review
dismissal was relaxed. Seventh consecutive clean probe at the corrected
read-back. Standing rule strengthened: restore bodies always carry the
review flags explicitly; derive keeps snapshot review flags verbatim;
the read-back — never the PUT exit code — is the contract. Record:
`28Sep2026-f9m02-restore-put-semantics-drift.md`. Snapshot: HEAD
`8063380` (PR #101 merged 2026-09-28) + this wave.

Updated 2026-09-29 (morning, R-14 live corroboration + R-13 seventh
occurrence): the 29Sep 09:37 IST paste member is collapse #10 —
containment 13/19 lines inside the 08:57 IST member, delta is the
risk-prioritization tail itself (mid-wave transcript class: created
before the 30Sep ops window it defers to). Tail claims verified live,
row by row: register rows R-01/R-05/R-08/R-12/R-13/R-14 present with
the cited due dates and fix-shape options (RISK-REGISTER.md:447-460);
ADR-0016 present (`docs/adr/0016-defer-cycle-latency-budget-wire-benchmark-gate.md`)
and TODO-3 answered by it; PR #73 MERGED 2026-09-25 (signal-outcome
instrumentation landed); wave-1 sentinels live (`insufficient_history`
in `src/loats/rules.py`, `composite_strength_threshold` 0.6 at
`src/loats/config/settings.py:68` with pinned test); P5 span quartet
green (snapshot mtime 1.0 min, `last_sampled_at` within a minute of
the probe, `kill_switch_verified:true`, `unhandled_exceptions:0`,
`ended_at:null` = in-progress by design). NEW live evidence for the
R-14 fix shape (29Sep rotation scan, 01:28-04:23Z): 5,172 budget
warnings, median 1,424 ms — the 28Sep total-cancellation regime (8 s
pins only) is NOT reproduced, BUT from 03:26Z values pin at ~8,000 ms
AND maxima run 9.2-12.6 s THROUGH the 03:45Z REGULAR open (155 lines
exceed 8,000 ms; max 12,630 ms), proving DEFERRED cancellation:
`asyncio.to_thread` executor futures cannot be cancelled mid-download,
so the window closes only when the in-flight sync `Article.download()`
returns (`sentiment.py:164,168-169` → `:214`). Sweep cost still
degrades monotonically (300 ms → 1.6 s → 8 s pins → over-window),
i.e. the 28Sep starvation curve re-forming with the article-TTL cache
slowing it. Contrary observability finding: sentiment persistence is
HEALTHY through the degradation (323 signals today, latest 04:15:00Z,
`degraded:false`, score 0.707, news_count 55) — zero liveness alerts
is CORRECT, so fix-shape option (iii) (analysis-liveness row) cannot
discriminate this failure mode and must not be chosen on liveness
grounds alone. Seventh R-13 occurrence: 08:45-08:55 IST pre-open
host-unreachable storm (first refusal 03:15:46Z, last 03:25:37Z,
4,699 quote refusals + 132 connection failures, zero after 03:45Z,
all five breakers CLOSED after recovery) — self-healed; the
sixth-occurrence conclusion (rollover-window grace alone cannot cover
the class) is unchanged. Implication for 30Sep: bounds must apply to
the DOWNLOAD leg (per-download timeout + concurrency cap), not just
the sweep — (ii) cache-deferral narrows but cannot bound the in-flight
leg; (iv) escalation should key on over-window maxima, which persist
while the liveness row stays green.

Updated 2026-09-29 (10:45 IST, collapse #11 — 08:53 member residual
verdicts): the 05:43Z composer-paste member is the family's eleventh
collapse — bulk is an OpenAlgo host-console log block (login → broker
callback → master-contract rebuild → option-chain 500s) plus two
parse-death PowerShell transcripts plus a verbatim re-slice of the
08:57 member's risk tail. Containment 0/202 against RISK-REGISTER.md
is the probe-target rule (log-block composition does not embed
register prose): the tail verifies claim-by-claim, not literally.
Both PS tails are parse-death by PS 5.1 semantics (literal
`<placeholder>` argv → `The '<' operator is reserved for future use`;
NOTHING on the line executed): intended operations verified live
instead — PR #104 MERGED as a58d58c with all 15 check-runs green
(Docker Build skipped by-design on a docs-only merge; advisory
benchmark-perf green), wave branch purged (empty ls-remote), protection
contract 0 divergences on BOTH surfaces (REST GET + GraphQL: 10
contexts strict, count 1, dismiss-stale true, enforce-admins on), tree
clean at ceiling 503/503. NEW live evidence: the host-console 500s
have a LOATS-side footprint — 12 `Could not find instrument/exchange
token for NSE_INDEX:NIFTY` API HTTP 500 events in LOATS structured
logs, all 2026-09-29 with last at 03:24:38Z, zero after 03:30Z, with
the `_fetch_history_bare` retry leg firing (Retry 1/3 after 1.02s);
recurrence scan over all six rotations finds 27SepT01×14 and
27SepT14×2 → defect CLASS: the host's delete-then-insert symtoken
rebuild (~43 s, delete 03:24:06Z → bulk insert 03:24:49Z) 500s
concurrent NSE_INDEX lookups and LOATS retry absorbs it (self-healed).
Disposition: host-layer transient absorbed by design; queued as a
30Sep ops-window question (defer analyzer data legs across the host
master-contract rebuild window, or idempotent backoff) behind R-14 —
not a new P1. All other tail claims verified live this session:
R-01/R-05/R-08/R-12/R-13/R-14 rows present, ADR-0016 present, PR #73
sentinels in the main tree (`insufficient_history`
src/loats/rules.py:513, `composite_strength_threshold` 0.6
src/loats/config/settings.py:68), P5 span quartet green (mtime 0.8
min, kill_switch_verified true, unhandled_exceptions 0). The 30Sep
ops window remains operator-gated.

Updated 2026-09-29 (12:10 IST, collapse #12 — roadmap re-slice, pool
unchanged): the 06:20 IST composer-paste member (fifth 29Sep member,
created AFTER the #104/#105 waves landed on main) is the day's twelfth
collapse. Containment 16/23 lines inside the 15Sep FR9 source archive
and 14/23 inside the 10:43 IST member; all 9 lines novel to the
sibling are the standing-risks header plus the verbatim STEP-3 Wave-3
block (F9-M-05, F9-M-01, F9-M-03, TODO-9) — ZERO novel finding lines;
unre-sliced pool UNCHANGED (§1-8, §17-21, Appendix). Every roadmap
item verified live at HEAD 44071c0 by two-sided sentinel grep:
`composite_strength_threshold` 0.6 and `opposition_threshold` 0.4 in
Settings (`src/loats/config/settings.py:68/78`); delta band
[0.50, 0.60] (`DELTA_BAND_LOW/HIGH`), `two_sigma_sell_band` and
`MIN_OI_CONFIRMATION` in `src/loats/strike_selection.py`;
`previous_hash` chain + grandfathered migration + link-walking
verifier (`verify_audit_log_integrity`, `src/loats/database.py:2731`)
with tamper tests (`tests/test_audit_chain_f9m01*.py`); TODO-8
answered by ADR-006 Amendment 7 (S-05 SUPERSEDED, no endpoint);
TODO-9's loud `insufficient_history` inside the TODO-1 IV-rank rewrite
(`src/loats/rules.py:513`; legacy silent 0.5 fallback absent from the
rules path). Remaining-risks block matches the register rows row by row
(R-01/R-05/R-08/R-12/R-13/R-14, 30Sep review, 08Oct span close; the
symtoken-rebuild question rides #11's disposition behind R-14). P5
span quartet green at record time (snapshot mtime 0.55 min,
`last_sampled_at` 06:34:55Z, `kill_switch_verified:true`,
`unhandled_exceptions:0`, `ended_at:null` = in-progress by design).
Register-append-only wave; tree clean, ceiling stays 503.

Updated 2026-09-29 (12:50 IST, collapse #13 — recomposition: risk
header swapped, roadmap re-included): the 07:09 IST composer-paste
member (sixth 29Sep member, created AFTER the #104/#105/#106 waves
landed on main) is the day's thirteenth collapse. Containment 18/24
lines inside the 15Sep FR9 source archive AND 18/24 inside the 10:43
IST member-12 sibling; the 4 lines novel to the sibling are the
recomposed standing-risks header (R-14 fix-shape + symtoken-rebuild
question still operator-gated, 30Sep discharge list, 08Oct span
deadline); the archive-novel delta is the re-included STEP-4 Wave-4
block plus the P5-GATE line member 12 lacked — ZERO novel finding
lines; unre-sliced pool UNCHANGED (§1-8, §17-21, Appendix). Wave-4
TODO states verified live at HEAD 5ea064e by two-sided grep:
TODO-10/S-14 and TODO-11/S-15 correctly OPEN (register-dated 30Sep,
gated on the R-01 decision and a supervised run respectively);
TODO-12 LANDED as F9-L-03 (`src/loats/signal_source_guard.py` +
`tests/test_signal_source_guard.py`, insert-time enum-source provenance
guard, fail-closed); TODO-16 answered by ADR-0020 (S-12 ACCEPTED,
binary switch + OPS limiter for the ANALYZE horizon); TODO-17 answered
by ADR-0019 (the CMP supersession register itself is the deliverable).
Remaining-risks block matches the register rows row by row (R-01/R-05/
R-08/R-12/R-13/R-14 with their dated due dates; "awaiting your word"
matches R-14's operator-gated status; R-05 01Oct and R-12 08Oct 08:02Z
span close verbatim). P5 span quartet green at record time (snapshot
`reports/p5_forward_test_20260924_080208.json` mtime ~1 min,
`last_sampled_at` 07:19:55Z, `kill_switch_verified:true`,
`unhandled_exceptions:0`, `ended_at:null` = in-progress by design).
Register-append-only wave; tree clean, ceiling stays 503.

Updated 2026-09-29 (14:55 IST, collapse #14 — member-13 recomposition
shape): the 09:15 IST composer-paste member (seventh 29Sep member,
created AFTER the #107 register wave merged at 13:12 IST) is the day's
fourteenth collapse. Containment 18/65 lines inside the 15Sep FR9
source archive, 0/65 against this register (stub-shape); the novel
delta is the member-13 standing-risks block verbatim (zero novel
finding lines), the re-included STEP-1-4 roadmap, and the day's only
LIVE evidence: pre-commit end-of-file + repo-hygiene (504 > 503)
failures reproduced at HEAD f9177a5 with a foreign `snapshot.json`
staged in the index — a UTF-16-LE PowerShell-redirect capture of the
branch-protection GET (the `gh api .../protection > snapshot.json`
verify-probe leg, mtime 14:43 IST, never committed, zero history).
The member's three PS 5.1 tails remain parse-time artifacts; their
intended operations verified live: PR #107 MERGED 07:42Z with the
remote branch already purged (ls-remote empty), tracked count read
504 explaining the hygiene tail, and a fresh protection GET
re-verified the full contract field-by-field (10 pinned contexts,
strict, approving=1, dismiss_stale=true, code_owner=false,
last_push=false, enforce_admins=true, force-push/deletions false, no
bypass key) — the parse-dead `verify-protection-contract` recipe's
intent discharged on live state. Fix: `/snapshot.json` ignored in
the quality-gate-output block (gitleaks-session precedent), index
restored to 503. P5 span quartet green at record time (snapshot
mtime 0.5 min, `last_sampled_at` 09:25:33Z,
`kill_switch_verified:true`, `unhandled_exceptions:0`,
`ended_at:null` = in-progress by design). Register-append-only wave;
tree clean, ceiling stays 503.

Updated 2026-10-02 (21:5x IST, compliance-evidence + live-state wave at
HEAD 6c8cf81, PR #119): the supervised span
`p5_forward_test_20260929_141804.json` closed GRACEFULLY at
2026-10-02T13:23:42Z (18:53 IST; 8 restarts, `kill_switch_verified: true`,
ended_at written) and NO live span exists since — two watchdog fresh-starts
(p5_forward_test_20261002_132352 / _132805) aborted within 8 s / 22 s with
`unhandled_exceptions=1` each; root cause live-verified two-sided: the
system's own log (13:28:25Z `Failed start Telegram bot: The token
`8848435922:***` was rejected by the server.`) and an out-of-band masked
getMe probe (HTTP 401, token never printed) against the .env value, whose
21:23 backup still carries the same dead token (no patch applied). The
revive-only watchdog (LOATS_P5_Watchdog, every 5 min; LOATS_P5_Resume
disabled) cannot heal this: supervisor pid 9324 (born 18:58 IST) still
holds the resume slot, so revival is BLOCKED on the operator's BotFather
token — then per R-16 the watchdog fresh-start starts the NEXT generation
and the 14-day accumulation clock moves to that span's `started_at`.
R-12's "grade span 141804 at the 13 Oct 19:48 IST mark" arithmetic is
therefore SUPERSEDED (the span closed early and gracefully, not graded);
the graded span is the next healthy one. Same wave: the compliance posture
moved from bulk assertions to `docs/COMPLIANCE-MATRIX.md` (R-18 row above);
PR #118 (hygiene pip-audit ignore, `53e194e`) still OPEN and untouched;
tree clean, ceiling 520->522 this wave.
