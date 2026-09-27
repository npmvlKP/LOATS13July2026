# 27Sep2026 — FR9-sections re-slice reconciliation (Testing §11, DevOps §12, Maintainability §9, Code-Quality §10)

Provenance: an evening paste presenting four sections of an "FR9-style
engineering review" (11. Testing Review, 12. DevOps Review, 9.
Maintainability Review, 10. Code Quality Review) arrived 2026-09-27
~20:20 IST while the P5 span
`reports/p5_forward_test_20260924_080208.json` was LIVE (mtime
advancing). HEAD at reconciliation: `ea6f78f` (PR #90 merge). Per the
supersession rules every section was reconciled against the archive and
the live tree before any work.

## 1. Re-slice proof — verbatim, not a fresh audit

All four sections are character-exact (markdown-scaffolding aside) re-
slices of `docs/audit-history/15Sep2026-FR9-forensic-review-report.md`,
the archived 15Sep FR9 forensic review, itself landed 15Sep (ratchet
history: "relocated from the staged root copy `15Sep2026-FR-ToDo
List.md`" — the archive's own §12 relocation note is the artifact the
paste presents as outstanding).

Containment evidence (this wave's live probe, whitespace/markdown-
normalized: `*`, `_`, `|` stripped, runs collapsed):

| Paste section | Archive anchor | Normalized containment |
|---|---|---|
| §9 Maintainability prose | archive line 206 | TRUE (exact-character TRUE pre-normalization) |
| §10 gate rows ×5 | archive lines 210-217 | TRUE |
| §11 Testing prose | archive line 221 | TRUE |
| §12 DevOps prose | archive line 225 | TRUE |

8/8 sections contained. The differences that defeat naive `in` checks
are pure scaffolding: the paste drops `**bold**` markers and renders
the §10 table with tab separators instead of markdown pipes.

## 2. Per-claim verdict table

| Paste claim | Live evidence at HEAD `ea6f78f` | Verdict |
|---|---|---|
| §11: "no property test caught the IV-rank constant (F9-C-01)" | F9-C-01/S-02 RESTORED 15Sep: loud `insufficient_history` sentinel live at `src/loats/rules.py:513`; 21-pin RED-first net `tests/test_iv_rank_f9c01.py`; supersession register S-02 | STALE — closed upstream |
| §11: "no test exercises routing-enabled end-to-end (F9-C-02's RED test)" | F9-C-02/S-05 closed 15Sep→18Sep: routing-guard nets `tests/test_p5_f9c02_routing_guard.py` (33 pins), divergence hard-FAIL grader, kill-switch span-proof nets, INVALID-EVIDENCE archive 18Sep | STALE — closed upstream |
| §11: "strike band/2SD untested because unimplemented" | F9-M-05 remediated 18Sep: closed 0.50-0.60 delta band, `estimate_bar_sigma()` 2σ sell side, OI confirmation fail-closed; 28-pin net `tests/test_strike_selection_f9m05.py` | STALE — implemented + netted |
| §11: "no liveness test for producer persistence" | F9-H-03 remediated 17Sep (cache-only refresh, per-source liveness alert, `sentiment_liveness_max_age_minutes`); BG-1 close-out 20Sep added the TTL-tier + freshness-chain nets | STALE — closed upstream |
| §11: "latency gates unenforced in CI" | `benchmark-perf` gate wired 17Sep, `.github/workflows/ci.yml:365-366` (advisory by ADR-0016; promotion to required context is bound to the 30Sep R-01 decision, per CONTRIBUTING) | STALE — gate exists; enforcement is a REGISTERED deferred decision, not a gap |
| §12: "branch protection (F9-M-02)" | CLOSED 24Sep (closure record + live GraphQL rule + GH006 direct-push rejection probe); drift-restored 25Sep (F9-M-02-R1); four consecutive clean re-probes since | STALE — closed upstream |
| §12: "benchmark gate absent (F9-H-02)" | Same as §11 latency row: present, advisory, evidence pack `25Sep2026-r01-benchmark-evidence-pack.md` cites 7 consecutive green advisory main runs 24-25Sep | STALE |
| §12: "this report is an untracked root artifact (relocate…)" | The relocation HAPPENED 15Sep — the paste quotes the archived copy's own pre-relocation sentence back at the tree the relocation already landed in | STALE — the paste's own advice is already executed |
| §12: "security workflow… results uninspected" | FR9 Wave 4 (23Sep) reconciled L-06: `security.yml` runs inspected green (register header, 2026-09-23 entry) | STALE |
| §9: "config-vs-plan drift has no conformance test (F9-H-01)" | F9-H-01/S-03 RESTORED (PRs #62/#63) with CMP-conformance pins: `tests/test_config.py:139-169` (composite 0.6 / opposition 0.4, hybrid-difference pin), `tests/test_trade_decision.py:794` | STALE — closed upstream |
| §9: "supersessions scattered (F9-L-05)" | ADR-0019 + `docs/CMP-SUPERSESSION-REGISTER.md` (S-01..S-15) landed 23Sep, content-pinned by `tests/test_cmp_supersession_register.py` | STALE — closed upstream |
| §10: "pytest 1841 / 1 skipped; 88.93 %; mypy 38 files" | 15Sep-session numbers, verbatim from the archive. Current at this HEAD (27Sep suite): see §3 below | STALE NUMBERS — superseded |

No pasted claim survives as an open work item.

## 3. Current gate snapshot at this HEAD

This wave's own verification run (repo venv, the CI-exact invocation):
see the register header paragraph for the recorded counts. The
qualitative §10 verdicts (all gates green) remain true; only the
absolute numbers moved since 15Sep (suite 1841→2290-class,
mypy 38→40 files, coverage ~88.93→~89.5 %).

## 4. New finding this wave — R-13 section lag (register self-consistency)

PR #90 (`2990240`) truthed up the R-13 TABLE ROW to recurring (Fri 25Sep
host-absent, Sat 26Sep rollover, Sun 27Sep documented window) but did
not touch the R-13 SECTION, which still read "single occurrence… zero
occurrences 24-26Sep" — a register-internal row/section contradiction
of exactly the class the register's own discipline exists to prevent.
Fixed in this wave: the section now mirrors the row (recurring
classification, the three dated occurrences, fail-closed/self-healed
outcome, evidence pointer to
`27Sep2026-p5-resume-counter-carry-reconciliation.md` §3). The
hardening decision itself is unchanged and still rides the 30Sep ops
window alongside R-08.

## 5. Wave contents

- This document (+1 tracked file; ratchet re-pinned 492→493 first — the
  tree was at-ceiling 492==492 pre-wave).
- `docs/RISK-REGISTER.md` — header paragraph appended (modification);
  R-13 section synced to the PR #90 row truth-up (modification).
- No source, test, CI, or dependency changes.

## 6. Recommended next step (unchanged)

The 30Sep ops window carries everything decisional: R-01 (ADR-0016
budget decision + benchmark-perf promotion), S-14/S-15 riders, R-08
bind-or-exit, R-13 hardening (now a recurring-pattern decision), R-12
span disposition (seed-carry vs successor — decide before the 08Oct
08:02Z earliest-valid close), plus the recommended mid-run Telegram
kill-switch exercise. Paste-family note: this is the sixth tracked
stale-paste reconciliation record since 26Sep (26Sep: F9L-block,
performance-review, console-probe; 27Sep: rollover/rebuild morning
window, P5-resume-counter-carry ops-window paste, this wave); the
archive-first containment probe (this wave's §1) is the cheapest first
check and collapses whole pastes before any per-finding work.
