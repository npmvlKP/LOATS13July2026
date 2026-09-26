# 26Sep2026 Paste Reconciliation — FR9 Low-Tier Block (F9-L-01/02/03) + P5 Decisional-Leg Record

- **Issue ID:** 26Sep paste reconciliation · **Category:** Paste lag /
  rider staging errata / P5 span evidence · **Confidence:** Certain (every
  verdict below is a live probe at the recorded snapshot, not a transcript
  read).
- **Status:** RECORD ONLY — no production code changed by this wave. The
  ADR-0016 mid-span freeze binds every enforcement constant and the
  trailing-stop enablement until the 2026-09-30 checkpoint; everything
  actionable here is documentation.
- **Snapshot identity:** HEAD `00d5b8c` (PR #85 merged 2026-09-26), clean
  tree, branch `docs/sep26-paste-reconciliation` created at the same SHA.
  Probes 2026-09-26T13:31–13:50Z. Protection read back field-by-field
  exact-contract (strict, 10 contexts, dismiss-stale, 1 approval,
  admin-enforced) — 6th consecutive clean watch. CI run `36230558303`
  green at HEAD.

## 1. Verdict table (paste claim vs live evidence)

| Paste claim | Live evidence at HEAD `00d5b8c` | Verdict |
|---|---|---|
| F9-L-01 (TODO-10) open P3, "30 min fix" | Dispositioned 23Sep (FR9 Wave-4); supersession register row S-14 OPEN, staged as a 30Sep R-01-decision rider; ADR-0016 freeze forbids pre-decision constant moves | STALE as an action item; CURRENT as a scheduled rider |
| F9-L-02 (TODO-11) open P3 | Row S-15, same disposition. Rider deliverables genuinely still PENDING: `tests/test_trailing_stop.py` has SL-M construction legs but no `Rule7ModificationLimitError` degradation leg (grep: zero hits in `test_trailing_stop*.py`) | STALE as an action item; rider work real and staged |
| F9-L-03 (TODO-12) open P3 | Guard live in-tree (`src/loats/signal_source_guard.py`, both write paths) since Wave-4; audited purge script in-tree; DRY-RUN record 23Sep enumerated 42 untagged + 1 STRESS-ORD. `--apply` NOT executed: live store re-counted 26Sep = 1 `modification_counts` row, `STRESS-ORD` present | PARTIALLY STALE — deliverable exists; the operator-timed maintenance window never ran |
| S-14 work order: "all THREE move in ONE commit" (`orchestrator.py:758/902/1045`) | Census at HEAD: FIVE producer budget sites carry the legacy constants — TA `0.03` @758, sentiment `0.04` @902, volatility `0.03` @1045, price-action `0.03` @1217, options-flow `0.03` @1369 | ERRATUM (§2) — executing the order as written would leave two stale producer surfaces under a RESOLVED row |
| S-15 work order: SL-M emission path at `orchestrator.py:2266-2269` | The Rule-7 SL-M surface sits at `orchestrator.py:2264-2285` at HEAD (`try/except Rule7ModificationLimitError` → audited refusal → `continue`) | ERRATUM (§2) — line drift since the `840ffca` pin; the fixture must pin semantics, not line numbers |
| (log block) `Stopping WebSocket execution engine`, master-contract redownload, `[LOGIN]` rows | These are OpenAlgo surfaces (`master_contract_db`, `websocket_execution_engine`, `auth` — fork tracked at `a51822b4`), not LOATS modules. LOATS feed health live-verified in the run log: `market_data_availability` breakers closed, producer calls succeeding | MISATTRIBUTED SURFACE — no LOATS action |
| `routed_decisions: 0` in the P5 run log | Reproduced live; root-caused strategy-legitimate (§3). Opened as R-12 | CURRENT — deadline-bound, see §3 |

## 2. Rider work-order errata (30Sep wave must land these corrections)

1. **S-14 surface census:** the order pins three sites; the tree has five
   producer budget-warning surfaces with the same pre-window constants.
   Per the order's own same-PR rule, ALL FIVE move in the ONE S-14 commit,
   each derived from the R-01 decision ADR's chosen semantics:
   `src/loats/orchestrator.py` lines at HEAD — 758 (TA), 902 (sentiment),
   1045 (volatility), 1217 (price-action), 1369 (options-flow).
   Non-producer budget surfaces (market-data 20 ms @1643, risk-mgmt 10 ms
   @1699, CMP-strategy 50 ms @1891, the 100 ms cycle target in
   `metrics.record_cycle_time`) are OUT of S-14's §1/§7 producer scope
   unless the decision ADR derives otherwise.
2. **S-15 pin:** cite `orchestrator.py:2264-2285` (HEAD `00d5b8c`), and
   write the fixture against the semantics (SL-M emission; Rule-7 budget
   exhaustion → audited `ratchet_refused_rule7` refusal, ratchet state
   consistent, position protected) — never against line numbers.

Register row text needs no edit: row S-14's authority wording
("§1/§7 latency-gate enforcement surfaces … 30/40 ms") already covers all
five constants generically; only the work-order body was wrong.

## 3. P5 decisional-leg accumulation (R-12, deadline 2026-10-08)

Live probes 26Sep:

- Run `reports/p5_forward_test_20260924_080208.json`: supervisor PID
  17272 resumed 12:39 UTC (5th writer claim), `kill_switch_verified: true`
  (latest event 12:39:39Z), all five source breakers closed, 1,342+
  cycles, `ended_at: null` (correct in-progress state — liveness verified
  by file mtime advancing during the probe window).
- Official validator grade (no-arg run at 13:45Z): **INCOMPLETE** —
  "no decisional activity recorded (routing counters all zero …); run
  still in progress".
- Root cause of zero routed attempts — **not a routing defect**. Signals
  persist and flow (226,564 total; 14,956 since span start; producers
  wrote 2,355 rows on 26Sep alone). The CMP gate is session-gated
  (`orchestrator.py:619`), and every trading-session cycle that reached
  it audited-rejected its candidates before any TradeDecision existed:
  24Sep 1,452 audit rows (770 `insufficient_strength`, 307
  `gating_rules_failed`), 25Sep 399 (102 + 8), 26Sep zero (Saturday —
  session closed, skip branch DEBUG-silent by design). No decision →
  `route_to_analyzer` never reached → `routed_decisions` legitimately 0.
- Consequence (mechanical, per `verify_p5_forward_test.py`): a span that
  ENDS with zero routed attempts grades FAIL on the decisional criterion
  — "outcomes with a zero attempt total cannot prove audited routing".
  Span started 24Sep 08:02:08Z; MIN_SPAN_DAYS=14 → earliest valid close
  08Oct 08:02Z. The attempt (if any) must land before `ended_at` exists.
- Operator options at the 30Sep checkpoint (CMP-owner decisions, not repo
  changes): (i) accept the FAIL-closed accumulation and record it — the
  span then evidences the SAFETY path (gates rejected every candidate,
  kill switch verified, breakers healthy) rather than the decisional
  path; or (ii) treat it as grader-true and schedule a successor span
  after a CMP review of the gate parameters that rejected every candidate
  across two full sessions. Register row R-12 tracks the deadline either
  way.
- Observation for the same review (no action this wave): producers persist
  signals on non-trading days too (2,355 rows on Saturday, incl. 453 BUY)
  — the session gate protects decisions, not signal storage. Pre-existing
  designed behavior, mid-span untouched per the freeze.

## 4. F9-L-03 `--apply` window (operator, NOT this wave)

Preconditions re-verified 26Sep: the 10-minute quiet window is satisfied
(last audit row 25Sep 15:29 IST), but the port probe will REFUSE while
the P5 supervisor holds :8001 — correct, its `Database` caches the F9-M-01
chain head and would fork the chain on its next write. `--allow-active-writer`
is NOT a safe bypass here: the supervisor resumes audit writes at the next
session and forks the chain regardless. Correct sequence: operator stops
the app (post-checkpoint, or a deliberate pause), runs
`python scripts/purge_legacy_signal_rows.py --apply`, confirms the
second-instance chain verification in the record, then restarts. The
backup + audit-first ordering in the script makes the window crash-safe.

## 5. Register actions this wave

- R-12 row (P3-watch, due 2026-10-08) + the dated register paragraph
  landed in the SAME PR as this record (house rule: register changes ride
  with their evidence).
- S-14/S-15 errata recorded here (§2); no supersession-register row text
  changes required (checked against the content pins in
  `tests/test_cmp_supersession_register.py`).

## References

- `docs/audit-history/15Sep2026-FR9-forensic-review-report.md` §Low tier —
  the block the paste re-carried verbatim
- `docs/audit-history/23Sep2026-fr9-wave4-low-tier.md` — the dispositions
- `docs/audit-history/25Sep2026-s14-s15-rider-work-orders.md` — the work
  orders this document corrects
- `docs/CMP-SUPERSESSION-REGISTER.md` rows S-14/S-15
- `docs/RISK-REGISTER.md` R-12; `scripts/verify_p5_forward_test.py` — the
  grading contract behind §3
