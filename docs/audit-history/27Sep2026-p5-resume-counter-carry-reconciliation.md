# 27Sep2026 — P5 resume counter-carry reconciliation (30Sep ops-window paste, §17 + §10 verification)

Provenance: the 30Sep ops-window planning paste (risk sequence §17, code-quality
review §10, scalability §7, reliability §8) arrived while the P5 span
`reports/p5_forward_test_20260924_080208.json` was LIVE. Per the
supersession rules every §17 claim was reconciled against the live register,
the running supervisor, the rotated LOATS logs and `data/loats.db` before any
work. This wave produced one code fix, two register truth-ups, and one paste
correction. HEAD at reconciliation: `285bd0d` (PR #89 merge).

## 1. §17 verification — risk sequence vs live register

| Paste claim | Live evidence | Verdict |
|---|---|---|
| 30Sep window: R-01, S-14, S-15, R-08 (bind-or-exit recommended), R-13 (three hardening options; ADR-0016 binds) | Register rows 265/272/277 match verbatim; S-14/S-15 are supersession-register riders staged for the 30Sep decision wave | CONSISTENT — no drift |
| ~08Oct: R-12, kill-switch event must land mid-run, routed still 0, exercise Telegram kill-switch before close | Row 276 matched the paste — but the "zero routed attempts" premise is FALSE (§2 below); `kill_switch_verified: true` events are supervision-start probes, one per generation (5 so far), which is what the grader's span-proof requires; a mid-run exercise is still recommended before close | PARTIALLY STALE — root cause found and fixed this wave |
| Paste §17 lists "R-14, R-15" | No such rows exist in the live register (table ends at R-13); grep over `docs/` finds no R-14/R-15 anywhere | PASTE DRIFT — rows do not exist; nothing to implement |
| §10: pytest 1841/1 skipped, 88.93% | Session-verified numbers at this same HEAD (`285bd0d`, 27Sep): 2288 passed / 2 skipped / 89.48%, mypy 38→40-file strict clean; the 1841/88.93% figures match an earlier wave | STALE NUMBERS — no live gap; re-verified in this wave's gates |
| §7/§8 scalability/reliability rows | Consistent with tree state at `285bd0d`; F9-C-01/F9-H-03/F9-C-02/F9-M-01 remain the open residuals | CONSISTENT |

## 2. R-12 root cause — the graded zero was an instrumentation defect

Evidence chain (all paths relative to repo root):

1. `logs/loats.log.3` (25Sep 08:42–19:51Z window) contains 289
   "Routing TradeDecision to Analyzer" lines and 289 "Successfully created
   and routed" lines, zero routing failures.
2. `data/loats.db` `trade_decisions` corroborates exactly: 289 rows on
   25Sep (hour bucket 09Z), newest `2026-09-25T09:59:54Z`, all status
   PENDING; 106 rows inside the span on 24Sep (08Z: 4, 09Z: 102). In-span
   total: 395 audited attempts.
3. The span's run log samples `counters` via
   `_sample_live_activity` (deltas over `counters_baseline`). Every CLI
   `--resume` is a fresh process whose engine counters start at zero, and
   `_effective_resume_baseline` computed
   `baseline = max(live − logged, 0)` — which floors to zero for a fresh
   engine, silently DISCARDING all prior generations' audited attempts.
   Six supervision generations are recorded in the span events (24Sep
   08:02, 24Sep 15:23, 24Sep 23:13, 26Sep 01:44, 26Sep 12:39, 27Sep 01:03
   — five restarts); the 26Sep 01:44Z resume wiped the 24–25Sep totals
   (the first resume after the 289 successes), so the register's "zero
   routed attempts through two full trading sessions" described the
   instrument, not the system.
4. The earlier reconciliation (`26Sep2026-paste-reconciliation-F9L-block.md`
   §3) read the same 25Sep window one-sided: its "25Sep 102+8" rejections
   match log.3's 110 "decision not created" lines exactly, while the 289
   successes in the same log were missed.

Fix (this wave, `fix/p5-resume-counter-carry`): the resume baseline IS the
logged total (pure carry). The next sample reports
`logged + (live_now − live_at_resume)`, which telescopes to true activity
when the engine survives a restart, adds exact post-resume work for a fresh
engine, and holds (never drops, never double-counts) across counter resets.
Pinned by `tests/test_p5_forward_test.py::TestResumeBaseline` including the
cross-process regression case.

30Sep disposition options (register row R-12): seed-carry the corroborated
395-attempt total into the graded stream via a supervisor provenance event,
vs successor span, vs record the fail-closed evidence. The fix makes every
FUTURE resume carry-continuous; it does not retroactively rewrite the live
log (grading remains fail-closed on the pre-fix stream by design).

## 3. R-13 classification correction — not a single occurrence

The register row said "first breaker storm / single occurrence" based on the
27Sep 06:46–06:58 IST window. The rotated logs hold the same fail-closed
storm signature at least twice before it:

- Fri 25Sep ~10:56–14:12 IST (`logs/loats.log.5` + `.log.4`, 05:26–08:42Z):
  ~14.8k "Circuit breaker 'openalgo' is open" cycle errors per rotated log,
  ~4.8k "No historical data for volatility analysis" — host-absent window
  (development session), all fetches refused, CMP never reached.
- Sat 26Sep 06:30–08:30 IST (`logs/loats.log.2`, 22Z–02Z buckets: 326 +
  2234 + 2045 errors): the daily ~06:30 IST host rollover, same signature.
- Sun 27Sep 06:46 IST: the documented storm (register R-13 original text).

Every occurrence: fail-closed held, zero decisions, self-healed, zero audit
residue. The hardening decision (rollover grace vs readiness probe vs
accept-as-designed) is unchanged and still rides 30Sep alongside R-08 — but
it is now a RECURRING-pattern decision, not a single-incident one.

## 4. Wave contents

- `scripts/run_p5_forward_test.py` — `_effective_resume_baseline` carry
  semantics (root-cause fix).
- `tests/test_p5_forward_test.py` — carry-semantics assertions rewritten,
  cross-process regression pin + baseline-keys pin added (RED first: 3
  failures against the pre-fix floor confirmed the defect, then GREEN).
- `docs/RISK-REGISTER.md` — R-12 row rewritten (instrument defect,
  root-caused, DB-corroborated 395-attempt population, one-sided-evidence
  correction); R-13 row truth-up (recurring signature, occurrences listed).
- This document.

## 5. Recommended next step (unchanged dates)

30Sep ops window (R-01 decision, S-14/S-15 riders, R-08 bind-or-exit,
R-13 hardening, R-12 span disposition) — now with the R-12 decision
informed by a fixed instrument: post-merge, every resume carries prior
generations, so the CURRENT span's remaining life accrues on top of its
logged totals going forward. A mid-run Telegram kill-switch exercise before
08Oct remains recommended (the grader's span-proof already passes per
generation, but a live exercise closes the operational question).
