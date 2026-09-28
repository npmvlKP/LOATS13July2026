# 28Sep2026 (00:46 IST paste) — FR9 §11 Testing + §12 DevOps re-slice reconciliation; ninth family member; the §9–§13 re-slice pool is exhausted

Provenance: a paste arrived 2026-09-28 00:46 IST (composer file timestamped
2026-09-27 19:16:18Z) carrying the same 19:55 IST host console plus
sections 11 (Testing Review) and 12 (DevOps Review) of the archived FR9
report, the pasted §13 risk block, the pasted "Prioritized remaining
risks" list, and a fresh failure tail (`gh pr create ... --body-file
<file>` dying in PowerShell 5.1). Reconciliation HEAD: `4201a02` (PR #92
merged 2026-09-27T18:29:48Z, merge commit `4201a0200bdc`; post-merge
main Pipeline run `36341230913` = success). This is the eighth tracked
stale-paste reconciliation record since 26Sep (ERRATUM 28Sep: the
merged revision over-stated this as "ninth" — seven records preceded
this one, three on 26Sep and four on 27Sep) and the ninth member of
the 27Sep paste family.

## 1. Re-slice proof — verbatim, not a fresh audit

- §13 Risk Matrix: 25/25 normalized lines BYTE-IDENTICAL to the 23:18
  night paste already reconciled by PR #92 (normalized containment,
  whitespace/markdown scaffolding stripped). No new §13 content.
- Console block: byte-identical head to the 20:01 paste (verified in the
  #91 and #92 reconciliations by direct diff of the composer files; the
  19:55 console is common family context).
- NEW content this member = §11 + §12 only. Both verbatim from the
  archive: §11 matches `15Sep2026-FR9-forensic-review-report.md` line
  221 (the full "Strongest suite in the chain (1,170 → 1,841 tests
  since FR8 ...)" paragraph, 8/8 distinctive fragments contained:
  1,170→1,841 growth, F8-C-01 fabrication cure, "no property test
  caught the IV-rank constant", producer-persistence liveness gap,
  routing-enabled e2e gap, strike-band-untested-because-unimplemented,
  "latency gates unenforced in CI"); §12 matches line 225 (repo-hygiene
  venv/env/junk rejection, RSS manifest validation, ruff×3, mypy
  strict, bandit, pip-audit, pytest + per-module floors, docker on PRs,
  security workflow weekly-carried, metrics :8001, F9-M-02 branch
  protection, F9-H-02 benchmark gate, "untracked root artifact"
  relocation note). 12/12 fragments contained; the only deltas are the
  markdown `**Gaps:**` bold markers the console transcription strips.
- Family delta-forensics (consecutive composer-file diffs, all four
  members): 20:01 → §9 Maintainability + §10 Code Quality; 23:18 → §13
  Risk Matrix; 00:46 → §11 Testing + §12 DevOps. The family has now
  re-sliced every one of the archive's §9–§13 sections. The
  tail-sections pool is EXHAUSTED.

## 2. Per-claim verdict table (§11/§12 rows vs live tree at `4201a02`)

| Paste claim (§11/§12) | Live evidence | Verdict |
|---|---|---|
| "1,170 → 1,841 tests / 88.93 % / mypy 38 files" (§11 figures) | Archive-era figures. Session suite at this HEAD: 2,290 passed / 1 skipped (by-design cov-lock guard), branch coverage 89.49 % (7,298/8,001), mypy strict clean on 40 files — pinned by the PR #91 record and unchanged by the docs-only #92 wave | STALE — archive-era numbers |
| "no property test caught the IV-rank constant (F9-C-01)" | RESTORED 15Sep: loud `insufficient_history` sentinel live at `src/loats/rules.py:513` (re-grepped this reconciliation; legacy `return 0.5` grep on the rules path empty), 21-pin RED-first net `tests/test_iv_rank_f9c01.py` present | STALE — closed upstream |
| "no liveness test for producer persistence" / "sentiment producer dead" implication | F9-H-03 remediated 17Sep (cache-only refresh, per-source liveness alert), BG-1 close-out 20Sep; Sunday-evening storm served as positive control: 5,767/5,767 sentiment calls, zero breaker rejections (PR #92 record §4) | STALE — closed upstream |
| "no test exercises routing-enabled end-to-end (F9-C-02's RED test)" | F9-C-02 closed 15Sep→18Sep: routing-guard nets (33 pins), divergence hard-FAIL grader, kill-switch span-proof nets; R-12 instrument defect itself root-caused and fixed by PR #90 | STALE — closed upstream |
| "strike band/2SD untested because unimplemented" | Implemented 18Sep: 0.50–0.60 delta band, `estimate_bar_sigma()` 2σ sell side, 28-pin net `tests/test_strike_selection_f9m05.py` present | STALE — closed upstream |
| "latency gates unenforced in CI" (§11) / "benchmark gate absent (F9-H-02)" (§12) | `benchmark-perf` gate PRESENT at `.github/workflows/ci.yml:365` ("benchmark-perf (F9-H-02 prerequisite, advisory)", `scripts/benchmark_performance.py` fail-closed), advisory per ADR-0016; enforcement/promotion is R-01 (P1, due the 30Sep ops window, 25Sep evidence pack) | STALE — registered deferred decision, not a gap |
| "repo-hygiene (venv/env/junk rejection), RSS manifest validation, ruff×3, mypy strict, bandit, pip-audit, pytest + floors, docker on PRs — all verified present, runs green" | Re-verified present in `ci.yml` this reconciliation; main Pipeline run `36341230913` = success (post-#92) | VERIFIED LIVE — no gap |
| "Security workflow present (weekly; results uninspected — carried)" | Carried item closed: `security.yml` runs inspected green by the FR9 Wave 4 reconciliation (register, 23Sep; broker-side idempotency stays carried by design) | STALE — carried item closed 23Sep |
| "Metrics :8001 wired with cycle/chain counters" | Era-neutral fact; unchanged — no action | TRUE, no action |
| "Docker: multi-stage, non-root, no dev extras" | Era-neutral fact; unchanged — no action | TRUE, no action |
| "branch protection (F9-M-02)" absent | CONTRADICTED LIVE at this reconciliation: GraphQL `branchProtectionRule` read-back — pattern `main`, `isAdminEnforced: true`, `requiredApprovingReviewCount: 1`, `dismissesStaleReviews: true`, the 10 required contexts (isort, flake8, bandit, deps-sync, ruff-lint, ruff-format, commit-lint, mypy, pytest-coverage, pip-audit); `GET /branches/main` → `protected: true`. Clean field-by-field read-back on BOTH surfaces pre-merge and post-restore (ERRATUM 28Sep: the merged revision's "ninth consecutive" ordinal was unverifiable and is retracted; no per-wave ordinal ledger exists) | STALE — contradicted live |
| "this report is an untracked root artifact (relocate to docs/audit-history/ before release)" | The relocation the section demanded HAPPENED: `15Sep2026-FR9-forensic-review-report.md` lives in `docs/audit-history/` — the document being re-sliced is the archived copy | STALE — already satisfied |

No pasted claim survives as an open work item.

## 3. Failure-tail attribution (reproduced live, not assumed)

- Pasted tail: `gh pr create --head docs/sep27-night-riskmatrix-reslice
  --base main --title "..." --body-file <file>` → `At line:1 char:95
  ... The '<' operator is reserved for future use. ...
  RedirectionNotSupported`.
- LIVE REPRODUCTION this reconciliation: `powershell.exe -NoProfile
  -Command 'echo <file>'` → byte-equivalent ParserError
  (`RedirectionNotSupported`, exit 1). Root cause: the literal
  `<file>` placeholder token, transcribed verbatim from a report's
  template command into PowerShell 5.1, where `<` is a reserved
  redirection operator. PS 5.1 fails at PARSE time — NOTHING in that
  line executed, by PowerShell's own semantics.
- The operation the tail intended SUCCEEDED: PR #92
  (`docs/sep27-night-riskmatrix-reslice` → `main`) was created,
  CI-green, merged 2026-09-27T18:29:48Z as `4201a02`, its branch purged
  (ls-remote empty both surfaces), post-merge main run `36341230913`
  success. The real create ran with `--body-file` pointing at the
  actual PR-body file (scratch artifact present, 23:47 IST). The tail
  is a transcription artifact of a report line, not an outcome.

## 4. Findings this wave — none new; two corroborations

- No new breaker activity: post-recovery scan of `logs/loats.log`
  (15:00:50Z recovery → 00:52 IST scan) finds ONLY the three
  CLOSED-after-recovery lines (final: `source:options_flow` CLOSED
  15:00:50.58Z) — zero OPENED events, zero refusals. R-13 remains at
  FOUR occurrences; no fifth.
- P5 span live and healthy: snapshot mtime 00:48 IST, `last_sampled_at`
  19:22:13Z, `cycles_completed` 529, `kill_switch_verified: true`,
  `unhandled_exceptions: 0`. The 30Sep/08Oct disposition inputs are
  unchanged.
- Structural note for the next family member: every FR9 §9–§13 section
  has now been re-sliced and reconciled. A further member carrying only
  already-seen sections collapses entirely under the archive-first
  containment probe + consecutive-paste diff; only genuinely new
  material (new sections, new console windows, new failure tails)
  deserves fresh verdicts.

## 5. Wave contents

- This document (+1 tracked file; ratchet re-pinned 494→495 first —
  the tree was at-ceiling 494==494 pre-wave).
- `docs/RISK-REGISTER.md` — header paragraph appended (modification).
- `scripts/ratchet_baseline.py` — ceiling 494→495 + history entry.
- No source, test, CI, or dependency changes.

## 6. Recommended next step (unchanged)

The 30Sep ops window carries everything decisional: R-01 (CMP latency
decision per ADR-0016 + benchmark-perf promotion citing the 25Sep
evidence pack), R-08 bind-or-exit alongside R-13 hardening (four
fail-closed/self-healed occurrences as evidence base), R-12 span
disposition (seed-carry vs successor span vs FAIL-closed evidence —
decide before the 08Oct 08:02Z earliest-valid close), S-14/S-15 and
R-07 riders, R-05 shared-venv rebuild 01Oct, and the mid-run Telegram
kill-switch re-verify at the window. The archive-first containment
probe + consecutive-paste diff remains the cheapest first check for the
next family member.

## 7. Post-merge addendum (28Sep) — advisory benchmark flake on the main run; errata

- Post-merge main run `36363406997` attempt 1: conclusion `failure`,
  ALL 10 required contexts `success` — the merge was legal under
  protection; the sole failing job was `benchmark-perf
  (F9-H-02 prerequisite, advisory)`, fail-closed BY DESIGN (ADR-0016)
  on verdict `PARTIAL (9/10 latency-gate checks passing)`.
- Failing check (artifact `performance_benchmark_20260928_004630.json`):
  `cmp_validation.db_operations` — the ANALYZE round-trip DB stage,
  5 samples, P1 threshold 0.02 s, actual p95 0.0641 s, pass-rate 0.6
  (stage budget 0.02 s). The same stage's P5 check (threshold 0.1 s,
  p99 0.0689 s) PASSED, as did all 9 other checks. A 64 ms p95 on a
  5-sample percentile against a 20 ms budget is shared-runner latency
  jitter, not a code path change: the wave is docs-only, and the
  IDENTICAL commit passed the same gate on PR #93's own run ~30
  minutes earlier.
- First-occurrence proof: every visible prior main-Pipeline run
  (`36341230913` back through `36079281988`, PR #73 era) is `success`
  — zero benchmark failures in main history before this one.
- Retry proof: `rerun-failed-jobs` attempt 2 on the same commit →
  `conclusion: success`. Flake class: environment-side, self-clearing,
  advisory-only. Runner image floats (ubuntu-24.04, image release
  20260920.314.1 at the failing attempt).
- Suite identity at the merge HEAD `6515afb`: 2,292 passed / 0
  skipped, rc=0 single-process bare run (the two
  environment-conditional by-design skips did not fire: no parent
  coverage run holds the cov-lock guard's lock; vollib present in the
  shared venv).
- R-01 input (30Sep): promoting `benchmark-perf` to REQUIRED as-is
  converts this flake class into a merge-blocker. Promotion must first
  harden the db stage's sample basis (sample count and/or percentile
  basis vs the 20 ms budget) — record the decision dependency in the
  30Sep checkpoint.
- Errata against the merged revision of this record: the lineage
  count is corrected to eighth in the header, and the unverifiable
  "ninth consecutive" read-back ordinal is retracted in the F9-M-02
  row (the clean both-surface read-backs stand).
