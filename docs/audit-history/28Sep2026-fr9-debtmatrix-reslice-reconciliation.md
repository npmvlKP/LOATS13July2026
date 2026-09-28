# 28Sep2026 — FR9 debt-matrix re-slice reconciliation (§14 Technical Debt Assessment + §13 Risk Matrix)

Provenance: a 28Sep morning paste presenting the OpenAlgo host console
(06:42:32–06:44:49 IST: rollover token-stale errors, user login 06:43:23,
broker connect 06:44:04, master-contract rebuild 109,485 symbols, healthy
option-chain recovery), followed by the FR9 report's §14 Technical Debt
Assessment and §13 Risk Matrix. This is the tenth member of the 27Sep paste
family and the ninth tracked stale-paste reconciliation record since 26Sep
(eight preceded it: three on 26Sep, four on 27Sep, one on 28Sep — per the
erratum-corrected arithmetic of `28Sep2026-sections-11-12-reslice-
reconciliation.md`). Reconciliation HEAD: the post-merge main of PR #94
(erratum + post-merge addendum wave).

## 1. Re-slice proof — verbatim, not a fresh audit

Normalized containment against the archived
`15Sep2026-FR9-forensic-review-report.md` (markdown-scaffolding aside,
per the register's table-normalization rule — separators mapped to
spaces, emphasis markers stripped):

| Paste section | Archive anchor | Normalized containment |
|---|---|---|
| §13 Risk Matrix (13 rows + header) | archive lines 227–243 | TRUE 14/14 |
| §14 Technical Debt Assessment (7 ranked items) | archive lines 245–253 | TRUE 7/7 |

Probe notes recorded for reproducibility: the first containment pass
returned 0/22 with separators DELETED (cells concatenated); mapping
separators to SPACES per the register rule resolved §13 to 14/14. §14
resolved 7/7 only after stripping the archive's `1.`–`7.` list
numbering — the paste dropped the ordered-list markers in copy, a pure
scaffolding delta; zero content differences. §13's content is identical
to the night paste's §13 (PR #92's containment), independently
re-proven here.

## 2. Per-claim verdict table — every row dispositioned upstream

| §14/§13 claim | Live evidence at this reconciliation | Verdict |
|---|---|---|
| F9-C-01 IV-rank saturated; BUY unreachable | S-02 RESTORED (15Sep): chain-IV rank, loud `insufficient_history` sentinel live at `src/loats/rules.py:513`, legacy silent 0.5 IV fallback dead; 21-pin net `tests/test_iv_rank_f9c01.py`; `-Infinity` boundary hardening (18Sep) | STALE — closed upstream |
| F9-C-02 P5 evidence invalid (flag divergence) | S-05 SUPERSEDED (ADR-006 Am.7): audited-attempt semantics; routing-guard nets (33 pins), divergence hard-FAIL grader, INVALID-EVIDENCE archive 18Sep; counter-carry fix PR #90 | STALE — closed upstream |
| F9-H-01 gate thresholds 0.5/0.6 vs CMP 0.6/0.4 | S-03 RESTORED (PRs #62/#63, `9f82a21`): composite 0.6 / opposition 0.4 conformance pins `tests/test_config.py:139-169` | STALE — closed upstream |
| F9-H-02 latency gate abandoned (0/816) | `benchmark-perf` gate wired `ci.yml:365-366`, advisory per ADR-0016; promotion is R-01's 30Sep decision; evidence pack cites 7 green advisory main runs; 28Sep addendum adds the flake-hardening input | STALE — gate exists; enforcement is the REGISTERED deferred decision |
| F9-H-03 sentiment producer dead since 13Sep | Closed 17Sep (PR #65, `07ab8ae`: LKG + cache-only refresh, per-source liveness) + BG-1 close-out 20Sep (TTL-tier nets) | STALE — closed upstream |
| F9-H-04 as_of_date never supplied | Closed 17Sep (`17Sep2026-F9H04-TODO5-resolution.md` + acceptance net `tests/test_f9h04_as_of_date_wiring.py`); closure re-verified LIVE at this reconciliation: the CMP step supplies `as_of_date or self._derive_history_snapshot_date(historical_data_objs)` at `orchestrator.py:1856-1857`; the scheduler's bare call is by design — derivation lives inside the CMP step where the input batch exists | STALE — closed upstream; call site verified |
| F9-H-05 P3 ensemble/decay/bounds absent | S-04: news leg delivered (PR #66, `633daae` — ensemble semantics, 4 h half-life decay, hard [-1,+1] bounds, ADR-0017); social 30 % leg is the REGISTERED residual (R-04, post-checkpoint producer wave) | PARTIALLY STALE — machinery landed; the leg deferral is a registered residual, not an open finding |
| F9-M-01 audit unchained | S-13 RESTORED (PR #54, `5f634ba`): `previous_hash` chain + walking verifier; F9-M-01-R1 frozen-chain-head re-anchor + concurrency net | STALE — closed upstream |
| F9-M-02 branch protection absent | Closed 24Sep; drift restored 25Sep (F9-M-02-R1). CONTRADICTED LIVE at this reconciliation: GraphQL `branchProtectionRule` — pattern `main`, `isAdminEnforced: true`, `requiredApprovingReviewCount: 1`, `dismissesStaleReviews: true`, the 10 required contexts; `GET /branches/main` → `protected: true` | STALE — contradicted live |
| F9-M-03 intake deferred | Resolved 18Sep by ADR-006 Amendment 7 / PR #56 (S-05 SUPERSEDED — audited-attempt semantics, read-only telemetry intake) | STALE — resolved upstream |
| F9-M-04 silent 0.5 fallback | Killed in the F9-C-01 wave (S-02 same resolution; the loud sentinel + the 18Sep JSON-boundary hardening) | STALE — closed upstream |
| F9-M-05 strike band/2SD off-spec | S-06 RESTORED (PR #55, `7014186`): closed delta band 0.50–0.60, 2σ sell side, OI confirm fail-closed; 28-pin net | STALE — closed upstream |
| F9-L-01…06 (noise, trailing default, store hygiene, kill-switch states, supersession register, carried set) | L-04/L-05 CLOSED (ADR-0020 / ADR-0019 + register, content-pinned); L-03 guard live both write paths, purge staged; L-01/L-02 = S-14/S-15 30Sep riders (freeze-bound); L-06 security.yml inspected green 23Sep | STALE — dispositioned (FR9 Wave 4, 23Sep) |

All 20 §13/§14 rows resolve closed/registered. No pasted claim survives
as an open work item.

## 3. New finding this wave — R-13 FIFTH occurrence (28Sep morning rollover storm)

Host attribution first (per the register's log-signature rule): every
console signature in the paste (`Initializing Strategy Module DB`,
`Order-update adapter not started`, `Order-update WS connected`,
`Strategy pending-stop reconciliation`, `Bulk insert completed`) is an
OpenAlgo host-checkout emitter — zero LOATS-tree hits for all five
strings, and no pending-stop job exists in LOATS source. The console
block is host traffic sharing the log stream.

The LOATS side was NOT silent in the corresponding window. Structured-log
forensics at this HEAD (json-parse-first, UTC `logs/loats.log`):

- Storm span 00:43:31Z→01:14:58Z (IST 06:13–06:44): first OPENED
  `2026-09-28T00:43:31.959123Z`, final `CLOSED after recovery`
  `2026-09-28T01:14:58.525490Z`.
- Counts: 145 per-source OPENED events (= 29 full cycles × 5 breakers),
  1,233 `Failed to get quotes: global circuit breaker open` fail-closed
  refusals, 5 CLOSED-after-recovery events (01:14:42–01:14:58Z), ZERO
  fallback-expiry 404s — the same zero-404 noise class as the 27Sep
  evening storm, not the 27Sep morning window's 102×404 profile.
- Forward scan after the 01:15Z cutoff: zero breaker hits in the
  remaining log (positive recovery evidence).
- Decisional funnel: zero decisions in-window (the single funnel-pattern
  match, `Enabled Analyzer routing` at 00:43:26Z, is a lifecycle line
  whose logger name matched the probe, five seconds BEFORE onset).
- P5 quartet healthy at probe: snapshot mtime 07:05 IST,
  `last_sampled_at` 01:35:23Z (minutes old), `kill_switch_verified:
  true`, `unhandled_exceptions: 0`; `ended_at: null` is correct
  in-progress state for the live span.
- Correlation: onset ~00:43Z precedes the paste console's first line
  (06:42:32 IST = 01:12:32Z); recovery aligns exactly with the host's
  06:44:04 IST broker login + master-contract rebuild completion. The
  daily-rollover correlation holds — fifth occurrence of the same
  fail-closed storm signature, every occurrence self-healed, zero
  decisions, zero fabricated data.

Classification: RECURRENCE (fifth), not first-occurrence — the R-13
watch row and section absorb it; hardening decision remains bound to
the 30Sep ops window (ADR-0016 freeze). No code fix in this wave.

## 4. Register delta (this wave)

Header paragraph appended; R-13 row truth-up (five occurrences 25–28Sep,
fifth window added); R-13 section evidence block + snapshot line
appended. Ceiling re-pin 495→496 (re-pin-first commit order). No other
register rows change.

## 5. Re-slice pool after this member

Remaining unre-sliced archive sections: §1–8 (findings tiers, reviews),
§15 (Production Readiness), §16 (Module-by-Module), §17 (Dependency
Overview), §18 (Roadmap), §19–21 (Executive/Architecture/Data-Flow),
Appendix. The pool is NOT exhausted — a further §14-or-§13-only member
collapses under this record's containment; new-section members still
need fresh verdicts.
