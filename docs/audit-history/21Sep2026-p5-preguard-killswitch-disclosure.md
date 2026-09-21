# 21Sep2026 - P5 Pre-Guard Kill-Switch Disclosure: R-02 Grader-Disclosure Amendment (ADR-0018)

**Status:** LANDED (verification evidence below, all gates green)
**Scope:** `scripts/verify_p5_forward_test.py`, `scripts/run_p5_forward_test.py`, `tests/test_p5_verifier_frozen_infra.py`, `tests/test_p5_f9c02_span_invariants.py`, `docs/adr/0018-p5-preguard-killswitch-disclosure.md` (new), `docs/RISK-REGISTER.md`
**Register items discharged:** R-02 (P1, decision required by 30Sep) — option 1, the grader-disclosure amendment, commissioned 2026-09-21.

## 1. Inputs (21Sep2026)

1. The tracked register's R-02 record: `scripts/verify_p5_forward_test.py`
   graded the live span `reports/p5_forward_test_20260916_140341.json`
   INCOMPLETE with `KILL-SWITCH PROOF IS NOT SPAN-ATTACHED ... writer
   generation(s) 1..3 lack the verification event`, and an ENDED run of
   that shape grades FAIL — a P1 verdict-blocker for the 30Sep checkpoint
   because generations 1..3 closed before the P5-OPS-01 verification probe
   existed (landed 19Sep).
2. The verifier's own re-derivation of the live event stream: generation 4
   opened 2026-09-19T01:06:52Z and carried its `kill_switch_verified` event
   11 s later (01:07:03Z); by 21Sep the artifact showed 9 generations
   (fresh-start + 8 claims) with generations 4..9 each proven (latest
   2026-09-21T04:38:09Z). The guard was live from the first guarded opening;
   generations 1..3 (openings 16..17Sep) are unprovable by construction.
3. The paste-lag precedent (R-06): the 21Sep paste still carried F9-H-03 as
   an open High finding; reconciled against git log and the tracked register
   before any action — F9-H-03 was already closed (PR #65 `07ab8ae`), and
   the paste's remaining risk table matched the register verbatim.

## 2. Root cause

- **RC-1 (the semantics artifact):** P5-OPS-01's span-attached criterion is
  temporal in nature ("every generation the operator could have proved must
  be proved") but was implemented without a vintage bound: an ENDED run
  hard-FAILs on ANY unproven generation, including writers whose code
  predated the probe and could not emit the event. Demanding the event from
  those writers demands the logically impossible; the gate conflates
  "unprovable" with "failed" and burns the span's otherwise-clean 14-day
  evidence on the artifact rather than a halt-path failure.

## 3. Remediation

### 3.1 Grader: vintage-derived disclosure (ADR-0018)

`scripts/verify_p5_forward_test.py`:

- `_span_kill_switch_generations` now stamps each generation with
  `opened_at` (fresh-start window: its FIRST recorded event; claimed
  generation: the `writer_claimed` stamp). No schema change — re-derived
  from the existing event stream.
- New pinned constant `P5_GUARD_CUTOFF = "2026-09-19T00:00:00+00:00"`
  (midnight UTC before the first guarded opening).
- New single-source helper `_pre_guard_kill_switch_generations(generations)`:
  unproven generations whose `opened_at` PARSES and precedes the cutoff.
  Unknown vintage (missing/empty/unparseable stamp) is never discloseable —
  it grades strictly, so the amendment cannot be stretched into an
  exemption and the frozen `TestGateWeakeningMutations` synthetic-stamp
  legs keep their exact meaning.
- `_grade_span_kill_switch_proof(run_log, reasons, ended, annotations=None)`
  splits the unproven set: pre-guard generations append a NON-GRADING
  disclosure to `annotations` (`NOTE:` lines in the CLI — the
  documented-outage pattern); post-guard/unknown holes keep the exact
  P5-OPS-01 hard-fail path. `grade_run_log` merges the disclosures into the
  annotation stream after the outage-notes rebind, so they surface on every
  verdict.

### 3.2 Supervisor: single-source live reporting

`scripts/run_p5_forward_test.py` gains `_pre_guard_generations`
(delegation to the official validator, matching the generation-model
pattern; version-skew fallback returns NO disclosure — a missing helper can
never fabricate one) and `_announce_span_invariants` now prints the
pre-guard `NOTE:` line plus a distinct clean-surface line
(`every post-guard writer generation verified (N guarded generation(s), M
pre-guard disclosed above)`), while post-guard holes keep the operator-facing
`[FAIL] ... verdict will be INCOMPLETE ...` surface unchanged.

### 3.3 Nets (RED-proven)

- `tests/test_p5_verifier_frozen_infra.py`: +7 legs landed RED-first
  (opening-stamp derivation, disclose-not-fail on the live shape, mixed
  pre/post-hole split, cutoff-boundary strictness, unknown-vintage
  strictness, end-to-end PASS-with-disclosure). RED evidence: 7 failed /
  13 passed with the verifier unamended; 20/20 green after.
- `tests/test_p5_f9c02_span_invariants.py`: the strict ended/ongoing legs
  re-based onto genuinely POST-guard shapes (19..20Sep stamps, window
  bracketed to Sep); the ongoing live shape pinned as disclosure-not-pending;
  the `--status` surface re-pinned (pre-guard NOTE + clean line, negative
  pins proving the old hard-hole phrasing is gone for pre-guard-only shapes)
  plus a new leg proving a post-guard hole still flags. 21/21 green.

## 4. Verification evidence (21Sep2026)

- Live grader on the ongoing run (rc=1, INCOMPLETE — correct: span 5.6d of
  14, genuinely ongoing): the `KILL-SWITCH PROOF IS NOT SPAN-ATTACHED`
  reason is GONE; replaced by
  `NOTE: kill-switch span proof: pre-guard writer generation(s) 1..3 opened
  before the verification probe existed (P5-OPS-01, cutoff
  2026-09-19T00:00:00+00:00) and could not emit the event -- disclosed,
  NON-GRADING (R-02 / ADR-0018) ...`; the 17Sep outage NOTE and data
  freshness are unchanged.
- Grader on the poisoned snapshot
  (`tests/fixtures/p5_run_log_20260912_150243_snapshot.json`, rc=1, FAIL):
  verdict PRESERVED — ROUTING DIVERGENCE VOID, the top-level
  `no kill-switch verification event recorded` reason, and span 3.96d < 14d
  all still fail the run; the old span-attached condemnation
  (generation(s) 1..6) is now the pre-guard NOTE. The disclosure masks
  nothing: a failing run keeps every other violation.
- Full P5/F9-C-02 suite (7 files): 165 passed
  (test_p5_verifier_frozen_infra, test_p5_f9c02_span_invariants,
  test_p5_f9c02_kill_switch_and_archive, test_p5_f9c02_outage_window,
  test_p5_f9c02_routing_guard, test_kill_switch_simple,
  test_p5_forward_test).

## 5. Citation rule

Cite this record for: the pre-guard disclosure semantics (ADR-0018), the
`P5_GUARD_CUTOFF` constant and its 19Sep-midnight justification, and the
unknown-vintage-fails-closed rule. The 30Sep grading checkpoint MUST read
the NOTE lines of the graded artifact's verifier output before citing run
20260916_140341, alongside the 19Sep record's market-data disclosures.
