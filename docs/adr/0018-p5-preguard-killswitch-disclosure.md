# ADR 0018: CMP P5 Kill-Switch Span Proof — Pre-Guard Generation Disclosure

## Status

Accepted — 2026-09-21 (R-02 decision, register option 1: grader-disclosure
amendment)

## Context

P5-OPS-01 (2026-09-19) made the CMP P5 kill-switch criterion SPAN-attached:
the official grader re-derives every writer generation from the run log's
event stream and FAIL-closes an ENDED run unless each generation carries its
own `kill_switch_verified` event. Applied to the live 14-day span
(`reports/p5_forward_test_20260916_140341.json`, started 2026-09-16T14:03:41Z),
this is structurally impossible to satisfy for the span's first three
generations: their writers ran pre-guard code that could not emit the event,
because the verification probe did not exist until the P5-OPS-01 wave landed
(19Sep). The verifier's own re-derivation shows generation 4 opening
2026-09-19T01:06:52Z and carrying its verification event 11 seconds later —
the guard was live from that instant — while generations 1..3 (openings
16..17Sep) are unprovable by construction.

`scripts/verify_p5_forward_test.py` therefore graded the run INCOMPLETE with
`KILL-SWITCH PROOF IS NOT SPAN-ATTACHED ... writer generation(s) 1..3 lack
the verification event`, and an ENDED run of that shape grades FAIL
(R-02, tracked in `docs/RISK-REGISTER.md`). Demanding the event from a
writer that could not emit it demands the logically impossible;
"unprovable" is not "failed". Left unamended, the 30Sep grading checkpoint
would read FAIL on the kill-switch criterion — burning the span's otherwise
clean 14-day evidence on a semantics artifact rather than a real halt-path
failure.

The register recorded two options: (1) a grader-disclosure amendment
mirroring the documented-outage annotation pattern (annotations are
NON-GRADING; an otherwise eligible run PASSes with disclosure) and the
P5-OPS-01 introduction pattern itself (re-derive from the event stream, no
schema change); or (2) accept FAIL-closed at the checkpoint. Option 1 was
commissioned 2026-09-21.

## Decision

1. **Vintage is derived, never declared.** Each generation gains an
   `opened_at` stamp computed by the single-source generation model
   (`_span_kill_switch_generations`): the fresh-start window opens at its
   FIRST recorded event stamp; a claimed generation opens at its
   `writer_claimed` stamp. No schema change to any run log — the stamp is
   re-derived from the existing event stream exactly like the generation
   model itself.

2. **The cutoff is a pinned constant: `P5_GUARD_CUTOFF =
   "2026-09-19T00:00:00+00:00"`.** Midnight UTC immediately before the
   first guarded opening (19Sep 01:06:52Z). Strictly-earlier openings are
   pre-guard; at-or-after openings grade exactly as P5-OPS-01 pinned them.
   A future probe change pins a NEW cutoff rather than re-meaning this one
   (the constant is named for replacement, and the comment in the verifier
   records the tuple semantics intent).

3. **Pre-guard holes disclose; they never grade.** Generations whose
   `opened_at` parses AND precedes the cutoff ride as a NON-GRADING
   disclosure annotation (`Grade.annotations` → CLI `NOTE:` lines), the
   documented-outage pattern (F9-C-02, 2026-09-17): the disclosure cannot
   enter `reasons`, so it cannot flip PASS/INCOMPLETE/FAIL. An
   otherwise-eligible ENDED run whose only holes are pre-guard now grades
   PASS with the disclosure visible to the 30Sep checkpoint.

4. **Everything else stays FAIL-closed.** Post-guard unproven generations
   hard-fail an ENDED run exactly as before. Unknown vintage — a missing,
   empty, or unparseable `opened_at` — grades STRICTLY (no disclosure):
   an unprovable hole whose vintage cannot be established fails closed, so
   the amendment can never be stretched into an exemption. Synthetic-stamp
   logs (the frozen `TestGateWeakeningMutations` legs) keep their exact
   pre-amendment meaning, proven by those tests staying untouched and
   green.

5. **Single source, supervisor included.** The disclosure set is computed
   by one helper (`_pre_guard_kill_switch_generations`) in the official
   validator; the supervisor's live reporting delegates to it (new
   `_pre_guard_generations` delegation, matching the generation-model
   pattern) so `--status` shows the operator exactly what the grader will
   conclude — live reporting can never drift from gate semantics. The
   version-skew fallback returns no disclosure: a missing helper can never
   fabricate one.

6. **RED/GREEN parity net.** Landed RED-first in
   `tests/test_p5_verifier_frozen_infra.py` (7 new legs: opening-stamp
   derivation, disclose-not-fail on the live shape, mixed-hole split,
   cutoff-boundary strictness, unknown-vintage strictness, end-to-end
   PASS-with-disclosure) and re-pinned in
   `tests/test_p5_f9c02_span_invariants.py` (the ended/ongoing strict legs
   moved to genuinely post-guard shapes; the pre-guard ongoing shape
   pinned as disclosure; the supervisor `--status` surface pinned for both
   the disclosed and the still-hard phrasings). All pre-existing pins that
   encode fail-closed semantics stayed untouched and green.

## Consequences

- The 30Sep checkpoint grades the halt path on its merits: every
  generation that COULD prove itself has proven itself (generations 4..9,
  latest verified 2026-09-21T04:38:09Z); the pre-guard generations appear
  as named disclosures, not as holes.
- The top-level kill-switch criterion is unchanged: an ENDED run without
  any `kill_switch_verified` evidence (e.g. the poisoned 12Sep snapshot)
  still FAILs via `_grade_kill_switch_evidence`.
- The disclosure names the cutoff and the ADR, so the checkpoint's audit
  trail is self-contained in the verifier output.
- Historical grading is stable: re-grading the 12Sep-era artifacts after
  this change yields the same verdicts as before (no run-log carries
  `opened_at`; stamps are re-derived; all their generations are either
  verified, top-level-unproven, or synthetic-stamped strict).

## Evidence

- Live artifact before: INCOMPLETE, reason `KILL-SWITCH PROOF IS NOT
  SPAN-ATTACHED ... writer generation(s) 1..3 lack the verification event`.
- Live artifact after: INCOMPLETE (run genuinely ongoing, span < 14d) with
  `NOTE: kill-switch span proof: pre-guard writer generation(s) 1..3
  opened before the verification probe existed (P5-OPS-01, cutoff
  2026-09-19T00:00:00+00:00) ... NON-GRADING (R-02 / ADR-0018)`.
- Nets: `tests/test_p5_verifier_frozen_infra.py` 20 passed (13 unchanged +
  7 new, RED proven at 7 failed / 13 passed before the verifier change);
  `tests/test_p5_f9c02_span_invariants.py` 21 passed; full P5 suite
  (7 files) 165 passed.
