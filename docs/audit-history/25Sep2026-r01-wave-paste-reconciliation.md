# R-01 Wave Staging Pack — 30Sep Checkpoint Reconciliation, Promotion
# Sequence and Rider Work Orders (25Sep2026, evening)

- **Issue ID:** R-01 wave staging (30Sep checkpoint) · **Category:** CMP
  compliance / decision-wave staging · **Severity:** P1 at the
  2026-09-30 checkpoint · **Confidence:** Certain (all verdicts live-probed
  2026-09-25 17:29 IST against HEAD `840ffca`)
- **Status:** STAGING PACK — makes NO decision, moves NO enforcement
  constant, changes NO server-side state. The ADR-0016 mid-span freeze
  binds until the 2026-09-30 checkpoint; this pack stages the decision
  inputs, the promotion sequence, and the rider work orders so the
  checkpoint wave executes in one pass.
- **Snapshot identity:** HEAD `840ffca` (PR #80 merged
  2026-09-25T10:16:19Z, post-merge Pipeline run `36123066955` = success;
  branch `docs/sep30-r01-checkpoint` created at the same SHA, zero
  divergence); local tree clean; live probes 2026-09-25 ~17:29 IST.
  Upstream drift check: `git ls-remote --heads origin` resolved exactly
  two heads (`main`, this staging branch), both at `840ffca`.

## 1. Paste reconciliation (the 25Sep ~17:25 IST ops queue paste)

| Paste claim | Live verdict at HEAD `840ffca` |
|---|---|
| Protection contract re-verified clean "just now" (incl. `dismiss_stale:true`); keep field-by-field read-back for every restore | **CONFIRMED INDEPENDENTLY** — fresh classic GET 17:29 IST: required contexts = the exact 10-context CONTRIBUTING contract (zero delta), `strict=true`, approvals=1, `dismiss_stale_reviews=true`, `enforce_admins=true`, force-pushes/deletions disabled. Read back field-by-field per the 25Sep F9-M-02-R1 lesson (the derived-restore body omitted `dismiss_stale_reviews` once; count-only read-backs are void). 5th consecutive clean probe since the restoration. |
| F9-M-03 — analyzer decision-intake deferred; USER DECISION (a) audited-attempt vs (b) intake endpoint | **STALE — RESOLVED 2026-09-18**: option (a) audited-attempt semantics accepted — ADR-006 Amendment 7, PR #56, closure record `docs/audit-history/18Sep2026-f9m03-audited-attempt-semantics.md`; supersession register row S-05 pins it ("Audited-attempt semantics instead (no endpoint)"); `tests/test_analyzer_intake_contract.py` pins the settings-field architecture (`analyzer_intake_path="analyze"` 404s by design, honestly-counted `error` outcomes); `verify_p5_forward_test.py` already grades under the accepted semantic. The pasted (a)/(b) fork was decided 7 days before the paste was written. No P5 "route ALL" gap remains open on this item. |
| R-01 (P1, 30Sep): decide (a) vs (b); promote benchmark-perf required in the same wave; close S-14/S-15 riders | **CURRENT but DATE-GATED** — matches the register row verbatim. Today is 2026-09-25 17:29 IST: the ADR-0016 freeze binds for 5 more days. Live span re-probed 17:29 IST (§3 below) is consistent with the pack's stabilization reading. Staging only (this pack). |
| R-07 (P2, 30Sep): process-tree kill vs frozen-tree guard | **CURRENT, deferred by design** — register R-07 row and the 23Sep incident record (`23Sep2026-orphaned-mutant-sweep-recovery.md`); candidates deliberately OPEN ("not one-key"); decision belongs to the 30Sep ops-review window. |
| R-08 (P2-ops, 30Sep): bind-or-exit pre-flight (recommended, 4 recurrences) | **CURRENT** — matches the register row verbatim (bind-or-exit recommended; four 24Sep recurrences). Touches the OpenAlgo checkout (a51822b4), not this repo's src tree. |
| R-05 (01Oct): shared-venv rebuild, then retire the fresh-venv workaround | **CURRENT** — register R-05 row, dated 2026-10-01; never mutate the shared venv mid-span (the P5 supervisor runs on it); fresh-venv pip-audit replication remains the standing push remedy until then. |

No code defect is live in the paste. The wave's deliverable at this date
is decision-wave staging, not remediation.

## 2. Decision-frame deltas discovered at HEAD (not carried by the paste)

These are executor traps the checkpoint wave must know before the first
commit:

1. **Required-context string trap.** The CI job's real check-run context
   is the full `name:` string — `benchmark-perf (F9-H-02 prerequisite,
   advisory)` (`.github/workflows/ci.yml:366`) — not bare
   `benchmark-perf`. A required context that no CI run produces wedges
   every merge. Promotion therefore sequences: land the `name:` rename
   first, observe a green run producing the new context, then PUT the
   11-context required list, then pin CONTRIBUTING (§5).
2. **R-01-close test-net trap.**
   `tests/test_risk_register_current.py::test_p1_items_carry_the_checkpoint_due_date`
   asserts exactly 2 P1 rows with R-01 `OPEN` and `2026-09-30` in the
   row. Closing R-01 at the checkpoint red-fails this pin unless the
   test is extended in the SAME commit (assert the closure record
   instead — the R-02 row is the in-file precedent).
3. **(b)-amendment metrics gap (do NOT fill mid-span).** The live
   `:8001/metrics` `cycle_time_stats` carries count/min/avg/max only —
   no histogram or percentiles. The evidence pack's (b) amendment needs
   no cycle percentiles (cadence + bounded producer window + stage
   budgets); any percentile surface belongs to the post-checkpoint
   producer wave, not to the decision commit.
4. **S-14 full surface.** The hardcoded producer budget warnings live at
   THREE sites, not one: `orchestrator.py:758` (TA, 30 ms),
   `orchestrator.py:902` (sentiment, 40 ms), `orchestrator.py:1045`
   (volatility, 30 ms). All three move in ONE commit, derived from the
   decision (see the rider work orders,
   `25Sep2026-s14-s15-rider-work-orders.md`).

## 3. Fresh live-span probe (17:29 IST, decision-neutral)

`http://127.0.0.1:8001/metrics`, continuous span since 16Sep:

| Field | 21Sep register | 25Sep pack (~15:17) | 17:29 IST probe |
|---|---|---|---|
| `count` | 2,183 | 26,413 | **27,557** |
| `target_compliance_count` | 0 | 0 | **0** (0.0%) |
| `average_seconds` | 4.48 | 1.430 | **1.663** |
| `max_seconds` | 206.1 | 48.243 | **48.243** (unchanged max — no new excursion) |
| kill switch | inactive | inactive | **inactive** |
| breakers | — | 4/4 healthy | **4/4 healthy** |

Reading: the stabilization reading of the 25Sep pack holds on a further
+1,144 cycles; max unchanged means no new worst-case excursion since the
afternoon probe. Only option (a) mechanics can move compliance above 0%.

## 4. Pre-staged decision brief (R-01 (a) vs (b) at the checkpoint)

Evidence authority: `25Sep2026-r01-benchmark-evidence-pack.md` (§2
runner-side: seven consecutive green advisory `benchmark-perf` main runs
24–25Sep, artifact `10854087767`, PASS 12/12, ANALYZE round trip
13.15 ms; §3 live span) plus the fresh §3 probe above.

- **(a) producer decoupling** — the only branch that moves cycle
  compliance above 0%; mechanics fold into the post-checkpoint producer
  wave per ADR-0016 §4 (one mid-span producer change instead of two;
  shares machinery with the F9-H-03 sentiment batching residue, R-04).
- **(b) ADR-amend the budget** — legitimizes the measured
  characteristics; the amended budget pins approximately: 1 Hz cycle
  cadence, bounded 8 s producer window, strike < 5 ms, trail < 1 ms,
  TA 80 ms, DB 20 ms, round trip 100 ms. Moves
  `metrics.record_cycle_time`'s 100 ms target and the health-check
  surface as ONE enforcement change, never mid-span.
- **Either way:** promote `benchmark-perf` to required in the same wave
  (§5), update supersession rows S-14/S-15, close R-01 in the register
  with the decision ADR (amendment to ADR-0016 or a successor), and
  extend the register test net in the same commit (§2.2).

## 5. 30Sep execution checklist (ordered)

1. **Step-0 reconcile:** fresh protection GET (field-by-field), fresh
   span probe, `git log --oneline -5`, `gh pr list` — confirm zero drift
   since this pack before executing anything.
2. **Decide (a)/(b)** against the evidence pack + §4; record the
   decision ADR; update `docs/CMP-SUPERSESSION-REGISTER.md` S-14/S-15;
   close R-01 in the register and extend
   `tests/test_risk_register_current.py` in the same commit; record the
   R-07 and R-08 ops-review outcomes in their register rows (same
   window, independent of the R-01 branch).
3. **Promotion sequence (both branches):**
   a. Commit 1: `ci.yml` job `name:` → `benchmark-perf` (the YAML key
      is already `benchmark-perf:`; the hygiene net pins the key, not
      the display name — pin-safe). CI must go green on the PR with the
      new context name present before anything server-side moves.
   b. Merge commit 1 under the standing contract (10 contexts).
   c. Save the live protection JSON; PUT the 11-context required list
      (byte-identical otherwise; `--input` takes a NATIVE Windows path).
   d. Commit 2: CONTRIBUTING pin — 11 required contexts, retire the
      "intentionally NOT in the required-context list" clause for
      benchmark-perf; ratchet history line for any new files in the
      same commit.
   e. GET read-back field-by-field (11 contexts, strict, approvals,
      dismiss_stale, enforce_admins); direct-push probe commit
      (`--no-verify`, reset immediately) expecting GH006 with
      "11 of 11 required status checks".
4. **Verification:** `pytest tests/test_repo_hygiene.py
   tests/test_risk_register_current.py
   tests/test_cmp_supersession_register.py
   tests/test_todo25_verifier_gates.py -q`, then the full battery per
   the quality-gates skill; ratchet re-pin per the single-source
   protocol if any file was added.
5. **R-05 executes separately on 2026-10-01** (shared-venv rebuild,
   then retire the fresh-venv push remedy). Do not fold it into the
   checkpoint wave.

## 6. Protection drill (standing, unchanged)

Every restore/protection PUT is read back field-by-field against
CONTRIBUTING's pinned contract (the `dismiss_stale_reviews` omission
lesson). Verification is surface-agnostic — the classic GET resolves as
of the 25Sep drift fix, the GraphQL `branchProtectionRule` field is gone
from the schema, and `GET /branches/main` -> `protected:true` is the
fallback; probe whichever resolve today, never conclude from one.

## References

- ADR-0016 (`docs/adr/0016-defer-cycle-latency-budget-wire-benchmark-gate.md`)
  — the freeze, the advisory gate, the promotion rule
- `docs/audit-history/25Sep2026-r01-benchmark-evidence-pack.md` — the
  pre-decision evidence pack this staging pack operationalizes
- `docs/audit-history/25Sep2026-s14-s15-rider-work-orders.md` — the
  rider work orders staged by this wave
- `docs/audit-history/18Sep2026-f9m03-audited-attempt-semantics.md` —
  the F9-M-03 closure the stale paste block re-carried
- `docs/RISK-REGISTER.md` R-01/R-05/R-07/R-08 rows and sections
- `docs/CMP-SUPERSESSION-REGISTER.md` rows S-05/S-14/S-15
