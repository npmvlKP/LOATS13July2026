# P5 Span Restart + Continuity Hardening Wave (2026-09-12)

**Date:** 2026-09-12 (Asia/Calcutta, Saturday). **Base:** `main` @ `393e3f4`
(merge of PR #26). **Tree before wave:** clean, `main` == `origin/main`,
stale `fix/p1-recovery-addendum` local branch deleted after checkout.
**Trigger:** execution of the P5 restart decision recorded in the 2026-09-12
operator handoff (P3 carried risk: "4299 cycles / 0 decisions predates the
weekend-session fix; the span without valid activity is unusable as
evidence"). **Method:** every disposition established against live process
state, the official validator's own grading (`grade_run_log`), and the
live Task Scheduler/cron surface — handoff narrative treated as claims,
re-verified before acting.

## Executed decision — P5 span restart (ADR-006 Amendment 6)

| Step | Evidence (2026-09-12 IST) |
| --- | --- |
| Writer-tree identification | PIDs 19756/19796 both running `run_p5_forward_test.py --resume`; creation times `18:18:48.4502363` / `.5924607` +05:30 (140 µs apart); `taskkill /T` confirmed 19796 is a CHILD of 19756 — the Windows venv launcher + real interpreter pair, a SINGLE writer, not a double-writer. The OS claim lock (`p5_forward_test_20260910_134427.json.claim`) was held; `--status` reported writer PID 19796 `[alive]`. |
| Watchdog race prevention | `LOATS_P5_Watchdog` DISABLED + `/End` before the kill window; re-enabled after the fresh run was confirmed claimed. |
| Honest termination | 134427 `operator_termination` event recorded, then `ended_at=2026-09-12T14:55:58Z`; official validator grade now **FAIL** (2.05d span, zero decisional outcomes, ended) — an honest FAIL instead of an INCOMPLETE carried forever. Pre-restart snapshot: `~/loats-ops/p5_134427_prerestart_snapshot.json`. |
| Fresh run started | `p5_forward_test_20260912_150243.json` started `15:02:43Z` (20:32:43 IST) via `~/loats-ops/p5_fresh_wrapper.cmd` + `p5_fresh_hidden.vbs` through a one-shot scheduled task (windowless, detached — 0xC000013A discipline). Writer PID 28688 claimed; routing enabled; cycles accruing within minutes. P5 14-day clock restarts; earliest gate PASS ~2026-09-26. |
| Watchdog continuity upgrade | The Amendment-5-era wrapper was resume-only: with 134427 ended it would have refused (rc=2) forever, leaving the evidence run unsupervised after any supervisor death. New wrapper order: (0) live-supervisor probe (`p5_supervisor_guard.ps1`) → nothing to do; (1) `--resume` (span-preserving); (2) fresh start ONLY when the newest run log is ended — an ongoing log with unresolved writer state never triggers a fresh fork (151114 second-writer class closed by construction). Verified end-to-end through Task Scheduler → VBS → wrapper → guard → correct decision + clean no-op against the live writer. |
| Route-watch repointed | Hermes cron script `p5_route_watch.py` (`RUN_LOG`, `RUN_ID`) now watches 150243; state file carries 134427's final honest snapshot (route_rows 0 / counters 0 across 11–12 Sep). |

## Finding 1 — cmd `>>` appends fail SILENTLY against the supervisor-held log (CLOSED this wave, machinery fix)

Wrapper trace lines and single-writer refusal echoes were absent from
`reports/p5_supervisor.log` whenever a supervisor was alive (e.g. the
12 Sep 07:54 IST "resume starting" line has no exit trace anywhere).
Root-caused empirically via scheduled-task probes: the same `echo >>`
succeeds to a dedicated file and silently produces nothing against
`reports/p5_supervisor.log` WHILE the supervisor (loguru) holds it open.
The failure class covers every diagnostic that mattered most during
writer disputes. Fix: all wrapper output now goes to the dedicated
`~/loats-ops/p5_watchdog.log`; nothing but the supervisor's loguru
stream ever touches the supervisor log. Recorded in ADR-006 Amendment 6 §4.

## Finding 2 — 12 Sep endpoint outage window root-caused (INFORMATIONAL)

Supervisor-log breaker forensics: OPENED cascade began `12:50:39Z`
(18:20 IST) — `openalgo` + source breakers; last OPENED `13:21:49Z`;
all CLOSED after recovery by `13:23:12Z` (18:53 IST), one minute after
the operator's OpenAlgo instance restart (`PID 30492` started
`18:50:59` IST, verified). The P1 confirmation pass (13:29Z / 18:59 IST)
ran against the restarted instance. The 5.5k breaker lines dated 13:00Z
were the degradation window's accumulated `open` retries, not
post-restart instability: 14:00Z onward is silent. The handoff's
P1′ recovery narrative is CONFIRMED by wire-level evidence.

## Live verification at close of wave

- Fresh run 150243: writer alive, cycles 133+ and accruing, 0 exceptions,
  routing enabled, `resume_refusal: None`.
- `LOATS_P5_Watchdog` (5-min) + `LOATS_P5_Resume` (logon) + `LOATS_P5_Status`
  (daily 09:00) all Ready on the new chain; watchdog next-fire exercised in
  production after the upgrade.
- Repo tree: only the two documentation files of this wave modified;
  branch protection on `main` untouched (PR route as always).
