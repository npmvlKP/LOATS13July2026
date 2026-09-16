# P5 Span Restart Execution Record (2026-09-16, FR9 condition closed)

**Date:** 2026-09-16 (Asia/Calcutta, Wednesday). **Base:** `main` @
`93fdd93` (merge of PR #46). **Tree:** clean (sibling-session addendum
filed in the follow-up commit of this wave). **Trigger:** execution of
the P0 register item — the 14-day span `20260912_150243` grades VOID
under the F9-C-02 self-verifying grader (15 proven
`routing_enabled:false` ROUTE rows inside its claimed-enabled span) and
the 16Sep re-check NO-GO; FR9 required an honest restart via the
ADR-006 Amendment 6 runbook.

## Sequencing decision

TODO-13 (F9-H-01, PR #46) was merged BEFORE the restart: a mid-span
threshold recalibration (composite 0.5→0.6, opposition 0.6→0.4) would
have left the fresh 14-day evidence window straddling two gate
calibrations, which the grader cannot detect. The fresh span runs
entirely under final CMP §4 calibration.

## Executed decision — honest END + fresh span (Amendment 6 discipline)

| Step | Evidence (2026-09-16 IST) |
| --- | --- |
| Pre-flight snapshot | `--status`: run `150243` ongoing, writer PID 12904 `[alive]`, span 3.96d, 0 exceptions, counters 70/0/0, `routing_divergence_detected: 0`; endpoint probe `Test-NetConnection 127.0.0.1:5000` → True. |
| Watchdog race prevention | `LOATS_P5_Watchdog` DISABLED before the kill window (`schtasks /Change` rc=0). |
| Honest termination | CTRL_C delivered to the detached supervisor console via `AttachConsole` + `GenerateConsoleCtrlEvent` (`~/loats-ops/p5_soft_stop.ps1`; `taskkill /F` ruled out — it orphans `ended_at: null`). The runner's finally-path wrote `ended_at=2026-09-16T14:01:53.516048+00:00`, `unhandled_exceptions: 0`, released the writer claim (claim file 0 bytes), disabled routing, and persisted the final sample (last sample 42 s before end). |
| Official grade of 150243 | `verify_p5_forward_test` rc=1: **FAIL / NOT-YET-PASSING** — 15 proven divergent ROUTE rows (evidence VOID) + span 3.96d < 14d. The honest FAIL replaces the void-able INCOMPLETE. |
| Fresh run started | `p5_forward_test_20260916_140341.json` started `14:03:41Z` (19:33 IST) by the production watchdog chain itself — resume-wrapper fresh-fallback fired on the now-ended newest log (`LOATS_P5_Watchdog` re-enabled + `/Run`); `routing.enabled_at_start: true`; writer pair PIDs 32944/4972 claimed. No manual wrapper override was needed: the Amendment-6 continuity upgrade performed the fork autonomously. |
| Route-watch repointed | Cron script `p5_route_watch.py` `RUN_LOG`/`RUN_ID` → `140341`; state file reset so the next 30-min tick establishes the new run's baseline. |
| Grading checkpoint re-armed | Cron `3c0a9c80d18d` rescheduled 26Sep → **2026-09-30 21:00 IST** (the 14-day mark 20:33 IST + 27 min). The 26Sep gate died with `150243`; the earliest legitimate PASS of the new span is **2026-09-30 20:33 IST**. |

## Supervision notes

- The `interrupted` event was not appended to the ended log: the
  pytest-asyncio Runner delivers cancellation as task-cancellation, so
  the finally-path (ended_at, claim release, routing disable) ran via
  the CancelledError branch while the event-append in the sibling
  except-branch did not. All grading-relevant invariants (ended_at,
  0 unhandled, released claim, final sample) are present and verified.
- `LOATS_P5_Resume` (logon) and `LOATS_P5_Status` (daily 09:00) were
  left untouched: the resume-wrapper's guard order handles the new
  ongoing log correctly (guard exit 1 = supervisor alive = no-op).

## Span vs gate

- New span started `2026-09-16T14:03:41Z`; 14-day mark
  `2026-09-30 20:33:41 IST`; grading checkpoint 21:00 IST same day.
- First supervised ROUTE-row lockstep check lands with the route-watch
  cron's next in-session tick (state baseline established 19:36 IST).
