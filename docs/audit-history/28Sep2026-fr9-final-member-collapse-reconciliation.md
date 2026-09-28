# 28Sep2026 — FR9 re-slice family: final §13/§14/§15-only member collapse

## 1. Member identification

This is the TWELFTH member of the 27Sep FR9 paste family and the eleventh
tracked reconciliation record. Its composition is exactly the one the #95 and
#96 records predicted collapses: the family router paragraph ("Re-slice Pool
& Prioritized Remaining Risks") followed by verbatim repeats of 15Sep report
§15 Production Readiness Assessment and §14 Technical Debt Assessment — and
NO new section. Per the pool-arithmetic rule, a member whose every section is
already containment-covered collapses as a whole; this record executes that
collapse and pins the live-state evidence at its HEAD.

Paste order note: the member presents §15 before §14 (the source report's
order reversed) — order is router cosmetics, not a delta signal.

## 2. Containment probe (normalized per-line)

Normalization per protocol: `*`/`_`/`|`/tabs → spaces, ordered-list markers
stripped, whitespace runs collapsed, per-LINE comparison only (never
whole-string, which can false-positive an entire section as one line).

| Paste block | Lines | Contained | Archive scope |
|---|---|---|---|
| §15 Production Readiness Assessment | 12 | **12/12** | 15Sep source lines 255-271 (via the #96 record's per-claim dispositions) |
| §14 Technical Debt Assessment (ranked) | 7 | **7/7** | 15Sep source §14 (via the debt-matrix record) |
| Router paragraph | 5 | 0/5 (expected) | Not archive content — live-verified claim-by-claim in §3 |

The §15 per-claim verdicts inherit from the #96 record without re-grading:
the only commits between that record's HEAD (`422b022`) and this wave's base
(`3732fe7`) are docs and the ratchet re-pin — the code state the #96
dispositions were measured against is bit-identical.

## 3. Router paragraph — claim-by-claim verification

| Paste claim | Live evidence at HEAD `3732fe7` | Verdict |
|---|---|---|
| "all REGISTERED — none new" | Every named risk carries a register row: R-01 (P1, due 2026-09-30), R-05 (Ops, due 2026-10-01), R-12 (P3-watch, due 2026-10-08), R-08 (P2-ops, due 2026-09-30), R-13 (P3-watch, hardening rides the 30Sep ops window), S-14/S-15 (supersession-register rows staged as the 30Sep riders) | CONFIRMED |
| R-01 30Sep: latency decision + benchmark-perf promotion, sample-basis hardening first (28Sep flake precedent) | Register R-01 row cites the 25Sep evidence pack and the same-wave promotion; the promotion precondition "hardening the stage's sample basis" is pinned verbatim in the register's wave record (the 28Sep advisory flake, attempt-2 same-commit success) | CONFIRMED |
| R-05 01Oct shared-venv rebuild | Register R-05 row, due 2026-10-01, unchanged | CONFIRMED |
| R-12 08Oct 08:02Z earliest valid close; carry-seed vs successor span vs honest FAIL-closed evidence | Register R-12 row states all three options and the deadline verbatim; live span still open (see §4) | CONFIRMED |
| Pool remains §1-8, §16-21, Appendix | Matches the #96 record §4 exactly | CONFIRMED |

## 4. Live-state probes at this HEAD

- **P5 span of record** (`reports/p5_forward_test_20260924_080208.json`):
  live and healthy — `cycles_completed` 2220, `last_sampled_at`
  2026-09-28T05:20:52Z (≈1 minute before probe), `kill_switch_verified`
  true, `unhandled_exceptions` 0, `ended_at: null` (correct in-progress
  state). Earliest valid close 08Oct 08:02Z unchanged; `routing.enabled_at_start`
  true with the resumed-run event stream intact.
- **Branch protection** — ELEVENTH consecutive clean read-back, both
  surfaces: GraphQL `branchProtectionRule` pattern `main`,
  `isAdminEnforced: true`, `requiredApprovingReviewCount: 1`,
  `dismissesStaleReviews: true`, the 10 required contexts (isort, flake8,
  bandit, deps-sync, ruff-lint, ruff-format, commit-lint, mypy,
  pytest-coverage, pip-audit); REST `GET /branches/main` → `protected: true`.
  The classic REST protection GET returned the documented migrated-rule
  rendering artifact earlier the same morning (a UTF-16 junk capture of the
  404 body sat untracked at the repo root; deleted, never staged, never
  committed) while the same surface rendered the full config minutes later —
  the surface is flaky, the rule is not: the null-render/404 remains a
  rendering artifact until the other surfaces contradict it, which they do
  not.
- **R-13 forward scan** — structured-log scan from the 01:15:58Z recovery
  cutoff to probe time across the live and rotated LOATS logs: 21,750
  records parsed (zero malformed), ZERO breaker events, no sixth storm. The
  count stays at FIVE occurrences. Watch-state unchanged; hardening decision
  remains bound to the 30Sep ops window (ADR-0016 freeze binds).
- **Post-merge main** — `3732fe7` (PR #96 merge) CI run `36378162598`
  conclusion `success`; local `main` synced to origin, clean tree.

## 5. Verdicts

- §15 gate table: STALE-BY-CONTAINMENT (12/12 verbatim). The NOT-READY
  verdict it carries STANDS — live capital stays gated on the dated chain
  (R-01/R-13/S-14/S-15 30Sep, R-05 01Oct, R-12 08Oct 08:02Z) exactly as the
  #96 record ruled.
- §14 debt matrix: STALE-BY-CONTAINMENT (7/7 verbatim); every F9 row was
  dispositioned upstream (debt-matrix record; #96 record for the §15 rows).
- Router paragraph: no new findings — every claim registered and current.
- **No new findings, no code changes.** The §13/§14/§15-only collapse
  predicted by #95 and #96 is executed; the unre-sliced pool is UNCHANGED
  (§1-8, §16-21, Appendix) because this member consumed no new section.

## 6. Snapshot

HEAD `3732fe7` (PR #96 merged 2026-09-28), post-merge main run `36378162598`
success. Wave: this record (+1 tracked file, ratchet 497→498) and the
register header paragraph (in-place modification). No other files.
