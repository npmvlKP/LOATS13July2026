# 27Sep2026 (night) — FR9 §13 Risk-Matrix re-slice reconciliation; R-13 fourth occurrence (Sunday-evening storm)

Provenance: a paste arrived 2026-09-27 ~23:18 IST carrying the 19:55 IST
console window plus section 13 (Risk Matrix) of the archived FR9
report. Reconciliation HEAD: `a2991c2` (PR #91 merged 2026-09-27).
This is the seventh tracked stale-paste reconciliation record since
26Sep, and the eighth member of the 27Sep paste family (morning
rollover/rebuild window, P5-resume-counter-carry ops paste, evening
FR9-sections re-slice, and this night paste).

## 1. Re-slice proof — verbatim, not a fresh audit

- Console block (46 lines, 19:55:55–19:56:18 IST): BYTE-IDENTICAL to
  the head of the 20:01-IST paste already reconciled by
  `27Sep2026-fr9-sections-reslice-reconciliation.md` (diff of the two
  paste files shows the console as common context; the only delta
  between consecutive family members is §13). No new console content
  arrived with this paste.
- §13 Risk Matrix: all 13 rows containment-TRUE (whitespace/markdown
  normalized: `*`, `_`, `|`, tabs stripped, runs collapsed) against
  `docs/audit-history/15Sep2026-FR9-forensic-review-report.md` lines
  227–243. 13/13 contained. The scaffolding delta defeating naive
  `in` checks is tab separators vs markdown pipes.

The paste family pattern holds: successive re-slices of the archived
15Sep FR9 report, each carrying a different section plus host-console
context. The archive-first containment probe collapsed this paste
before any per-finding work.

## 2. Per-claim verdict table (§13 rows vs live tree at `a2991c2`)

| Paste claim (§13 row) | Live evidence | Verdict |
|---|---|---|
| F9-C-01 IV-rank saturated; BUY unreachable | RESTORED 15Sep: loud `insufficient_history` sentinel at `src/loats/rules.py:513` (re-grepped this wave); 21-pin RED-first net `tests/test_iv_rank_f9c01.py`; register S-02 | STALE — closed upstream |
| F9-C-02 P5 evidence invalid (flag divergence) | Closed 15Sep→18Sep: routing-guard nets (33 pins), divergence hard-FAIL grader, kill-switch span-proof nets, INVALID-EVIDENCE archive 18Sep | STALE — closed upstream |
| F9-H-01 gate thresholds 0.5/0.6 vs CMP 0.6/0.4 | RESTORED (PRs #62/#63): CMP-conformance pins `tests/test_config.py:139-169` (composite 0.6 / opposition 0.4), `tests/test_trade_decision.py:794`; register S-03 | STALE — closed upstream |
| F9-H-02 latency gate abandoned (0/816) | `benchmark-perf` gate present at `.github/workflows/ci.yml:365-366`, advisory per ADR-0016; promotion decision is R-01, due the 30Sep ops window with the 25Sep evidence pack | STALE — registered deferred decision, not a gap |
| F9-H-03 sentiment producer dead since 13Sep | Remediated 17Sep (cache-only refresh, per-source liveness alert); BG-1 close-out 20Sep. Tonight's storm doubles as a positive control: the sentiment source served 5,767/5,767 calls with ZERO breaker rejections through the whole window (its cache-only path is immune by design) | STALE — closed upstream; live-behavior corroborated tonight |
| F9-H-04 as_of_date never supplied | Closed 17Sep (`17Sep2026-F9H04-TODO5-resolution.md`) | STALE — closed upstream |
| F9-H-05 P3 ensemble/decay/bounds absent | Closed 21Sep (`21Sep2026-F9H05-p3-ensemble-decay-bounds.md`) | STALE — closed upstream |
| F9-M-01 audit unchained | Closed 17Sep (hash chain) + R-1 frozen-chain-head resolution 24Sep | STALE — closed upstream |
| F9-M-02 branch protection absent | CLOSED 24Sep; drift-restored 25Sep (F9-M-02-R1); four consecutive clean re-probes. Live contradicting evidence AT THIS RECONCILIATION: protection GET returned approving=1, dismiss_stale=true, enforce_admins=true, strict=true, 10 required contexts | STALE — contradicted live by the protection read-back |
| F9-M-03 intake deferred | Closed 18Sep (audited-attempt semantics) | STALE — closed upstream |
| F9-M-04 silent 0.5 fallback | Killed 15Sep per S-02 (loud sentinel, fail-closed). The `return 0.5` hits in `src/loats/ta.py` are indicator neutral-values (RSI/CMF-style neutral midpoints), not the gate fallback; the rules-path grep for the legacy fallback is empty | STALE — closed upstream |
| F9-M-05 strike band/2SD off-spec | Implemented 18Sep: 0.50–0.60 delta band, `estimate_bar_sigma()` 2σ sell side, OI confirmation fail-closed; 28-pin net `tests/test_strike_selection_f9m05.py` | STALE — closed upstream |
| F9-L-01…06 | Dispositioned 23Sep (FR9 Wave 4: L-04/L-05 closed by ADR-0020/ADR-0019, L-03 guard live); F9L-block paste record 26Sep | STALE — closed upstream |

No pasted claim survives as an open work item.

## 3. Console attribution (no new analysis needed)

Every emitter line in the 19:55 IST window is an OpenAlgo
host-checkout emitter, re-verified by two-sided grep this wave
(LOATS `src/`+`tests/`: zero hits; `G:/.OA/OpenAlgo`:
`database/strategy_module_db.py`, `websocket_proxy/order_adapter.py`,
`utils/auth_utils.py` all carry their signatures). The window shows
the host restarting its strategy module and resuming the stored broker
session (unchanged, multi-session resume — live feed preserved) while
a Firefox dashboard fetched the NIFTY option chain. Host traffic
sharing the console with LOATS — not a LOATS ordering defect. What the
console does NOT show is that the host restart landed MID-STORM:
LOATS had been failing closed for 17 minutes when the host came back
up (§4).

## 4. New finding this wave — R-13 fourth occurrence (Sunday evening)

The evening FR9-sections wave recorded three occurrences 25–27Sep
(Fri host-absent, Sat rollover, Sun-morning documented window). A
FOURTH occurrence ran this evening, corroborated by three independent
surfaces (LOATS structured log, P5 supervision snapshot, host console
timing):

- Window: Sun 27Sep **19:38:49–20:30:50 IST** (14:08:49–15:00:50Z).
  Onset 14:08:49Z first global refusal; global + per-source breakers
  cycling OPENED from 14:09:12Z; host restart 14:25:55Z (the console
  window's own timestamps) — the storm PRECEDED the restart by ~17
  minutes, so the restart was a consequence/recovery attempt, not the
  cause; last refusal 15:00:34Z; final CLOSED after recovery
  15:00:50Z; zero breaker events after.
- Scale: **85** OPENED events (17 full cycles × 5 breakers: global
  `openalgo` + ta/volatility/price_action/options_flow);
  **3,373** fail-closed global refusals (`Circuit breaker 'openalgo'
  is open` / `global circuit breaker open`) across `logs/loats.log`
  (rotation at 14:08Z; the storm dominates the fresh log).
- Signature variation vs the morning window: ZERO fallback-expiry 404s
  tonight (morning: 102). The expiry-cache state differed — a second
  data point that the storm's noise profile is not fixed and operator
  triage guides must not pattern-match on the 404 tail alone.
- Decisional funnel: zero `Routing TradeDecision` events in the
  window (grep-verified) — fail-closed held, zero decisions, no
  fabricated data. Positive control: sentiment 5,767/5,767 zero
  rejections (cache-only path).
- P5 residue: supervision snapshot at 23:24 IST —
  `unhandled_exceptions: 0`, `kill_switch_verified: true` with in-span
  probes (latest 13:33Z generation start), `restarts: 6`, routing
  enabled at start, counters carried per PR #90 semantics. The span's
  30Sep/08Oct disposition inputs are unchanged by tonight's storm.

Register updates this wave: R-13 row and section truth-up (four
occurrences 25–27Sep, two of them Sundays, one spanning a host
restart). The 30Sep hardening decision (rollover-window grace vs
rebuild-aware readiness probe vs accept-as-designed) is unchanged and
now carries four fail-closed/self-healed occurrences as its evidence
base.

## 5. Wave contents

- This document (+1 tracked file; ratchet re-pinned 493→494 first —
  the tree was at-ceiling 493==493 pre-wave).
- `docs/RISK-REGISTER.md` — header paragraph appended (modification);
  R-13 row updated to the fourth occurrence (modification); R-13
  section updated (modification).
- `scripts/ratchet_baseline.py` — ceiling 493→494 + history entry.
- No source, test, CI, or dependency changes.

## 6. Recommended next step (unchanged)

The 30Sep ops window carries everything decisional: R-01 (ADR-0016
budget decision + benchmark-perf promotion), S-14/S-15 riders, R-08
bind-or-exit, R-13 hardening (evidence base now four occurrences),
R-12 span disposition (seed-carry vs successor — decide before the
08Oct 08:02Z earliest-valid close), plus the mid-run Telegram
kill-switch exercise (already satisfied: `kill_switch_verified: true`
with multiple in-span probes — re-verify at the window). The
archive-first containment probe remains the cheapest first check for
the next family member.
