# P5 Wednesday Decisional Re-check and Drought GO/NO-GO (2026-09-16)

**Date:** 2026-09-16 (Asia/Calcutta). **Base:** `main` @ `71682ea`.
**Tree:** clean (two stat-only index entries refreshed; zero content deltas).
**Scope:** read-only decisional re-check of forward-test run
`p5_forward_test_20260912_150243` (ADR-006 Amendment 6 restart). The
`20260912_134427` predecessor was honestly ended FAIL on its own evidence
and was not touched. No PIDs killed, no fresh fork performed.

## Writer health

- `run_p5_forward_test.py --status` at ~09:21 IST: run **ongoing**,
  writer **PID 12904 [alive]**, 1,322 cycles accrued since the
  2026-09-12T15:02:43Z start, zero exceptions, span 3.53d (gate >= 14d).
- Run-log last sample lag at check time: 52s (fresh writer).

## Evidence read (09:20-09:27 IST, all timestamps UTC -> IST +05:30)

1. `signal_validation_failed` today: **20** events, every one inside
   09:15:09-09:18:05 IST (`03:45:09Z`-`03:48:05Z`), i.e. inside the
   09:15-10:30 decisional window. Zero events after 09:18:05 IST.
   Each event is a cycle that formed no TradeDecision.
2. Breaker `OPENED` today: **40** events across
   `source:options_flow` / `source:price_action` / `source:volatility` /
   `source:ta` / `openalgo`, every one between 07:57:29 and 08:05:28 IST
   (`02:27:29Z`-`02:35:28Z`) - the pre-open startup transient class,
   self-recovering by design. **In-session (>= 09:15 IST) OPENED events: 0.**
3. ROUTE audit rows dated today: **35** by 09:27 IST (first
   `03:50:13Z`), all `status: success` on NIFTY decisions from
   `trade_decision_engine`.
4. Routing counters at the run-log sample taken 09:27 IST:
   `{'success': 30, 'disabled': 0, 'error': 0,
   'routing_divergence_detected': 0}` - success advanced 0 -> 14 -> 30
   across three samples within ~6 minutes, tracking the ROUTE-row count
   (35) at supervisor sampling cadence; error stayed 0 throughout.
5. REJECT audit rows dated today: **33**; reason-field occurrences
   observed across those rows: `insufficient_source_diversity` (40),
   `gating_failed` (13), `gating_rules_failed` (13) - consistent with the
   known low-VIX prudence-gating class, not the starvation signature.

## GO/NO-GO thresholds (rule from the re-check directive)

- Threshold 1 - new in-window (09:15-10:30 IST) validation rejections vs
  the 14 Sep baseline of 2,504: **BREACHED** (20 new in-window
  rejections, 09:15:09-09:18:05 IST).
- Threshold 2 - any in-session breaker OPENED event (0 allowed):
  **PASS** (0 in-session; 40 pre-open transients excluded).

**Verdict under the stated rule: NO-GO - DROUGHT-PERSISTING** (any new
in-window rejection forces NO-GO). Recommendation recorded for the
operator: early honest END of run `20260912_150243` plus an
evidence-preserved re-run. **This run performs the END only as a
recommendation; the operator action was not executed here.**

Mitigating observation (reported, does not override the rule): today's
drought lasted 9m56s and was confined to the open; from 09:20:48 IST the
pipeline routed 35 decisions with clean counters - materially better than
the 14 Sep all-day 2,504-rejection baseline. The operator may weigh this
when acting on the recommendation; the 26 Sep 20:32 IST gate remains the
earliest legitimate PASS either way.

## Span vs gate

- Elapsed at ~09:30 IST: **3.54d / 14d** (started 2026-09-12T15:02:43Z).
- Earliest legitimate gate PASS: **~2026-09-26 20:32 IST**
  (10.46d remaining).

## Independent verification addendum (09:41 IST, same morning)

The 09:30 route-watch snapshot and a direct re-read sharpen the
mitigating observation into a material fact:

- ROUTE rows today rose 35 -> **43**, every one `status: success`
  (NIFTY), `error=0`.
- Run-log counters at the 09:31 IST sample: `success=43, disabled=0,
  error=0, routing_divergence_detected=0` — **rows = counters exactly
  (43 = 43), `rows_unattributed = 0`**. Under the 14 Sep counter-
  mechanics proof (every outcome `_do_route_or_disable` writes bumps the
  supervised engine's own counter; foreign writers left 14 Sep's rows
  unattributed), this is the **first fully provenance-locked decisional
  evidence of the run**: the supervised writer itself produced and
  routed all 43 decisions.
- Drought summary for the day: 20 rejections in 9m56s at the open,
  clean routing from 09:20:48 IST onward; 0 in-session breaker opens;
  writer healthy (PID 12904, restarts now 5, sampling fresh).

Disposition impact: the NO-GO verdict stands **under the stated rule as
written** (any new in-window rejection), but its premise —
drought-persisting — is now contradicted by same-morning provenance-
locked success evidence. The early-END recommendation should be weighed
against this addendum; the rule itself (reject-any-at-open) may merit
re-scoping to sustained rather than transitory open-window droughts.
Recorded in-tree as this untracked file's addendum pending the wave
that commits it; ceiling at write time is 424/424 (zero headroom).

Close-of-day confirmation (16:00 IST digest): the day ENDED as it ran —
70/70 ROUTE rows attributed (unattributed 0), counters 70/0/0,
`routing_divergence_detected: 0`, 0 in-session breaker opens, 40
pre-open transients, rejections flat at 29 (open-window only), writer
fresh (72 s), restarts steady at 5, `disabled_routes_during_enabled_
window` unchanged at 15 (no new disables). Full provenance-locked
trading day; the drought signature did not return. This completes the
evidence base for the operator's early-END decision and favors HOLD to
the 26 Sep 20:32 IST gate.

Supersession note (21:10 IST, same day): the HOLD recommendation above
predates the operator action it advised on. Run 20260912_150243 was
ended honestly at 14:01:53Z (19:31:53 IST) on this evidence, and a
fresh span, p5_forward_test_20260916_140341, started 14:03:41Z
(19:33 IST) via the Amendment-6 watchdog chain — restart record:
16Sep2026-p5-restart-execution.md (PR #47). The 26 Sep 20:32 IST gate
died with 150243; the fresh span's earliest legitimate PASS is
2026-09-30 20:33 IST (grading checkpoint 21:00 IST same day).
