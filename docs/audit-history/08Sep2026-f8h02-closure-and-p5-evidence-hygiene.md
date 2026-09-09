# F8-H-02 Closure + P5 Evidence-Stream Hygiene Wave

**Date:** 2026-09-08 · **Base:** `358fcf0` (clean tree) · **Trigger:** the
production-readiness chain inherited from `docs/audit-history/01Sep2026-FR.md`
still listed F8-H-02 as an open blocker, and the 08Sep verification session
discovered fresh evidence-stream contamination during the external-verifier
sweep. This record closes both.

## Part 1 - F8-H-02 (Rule-7 per-order modification gate): CLOSED

**Finding (01Sep2026-FR):** the Rule-7 modification counter was
process-global, in-memory, and reset on restart; per-order semantics were
absent and no gate existed at the modify boundary.

**State discovered at HEAD `358fcf0`:** the implementation is PRESENT in the
tree (landed 2026-09-02, `ad59db6`, recorded in
`docs/audit-history/REPORT_CMP_RULES_7_11_IMPLEMENTATION.md`):

- `src/loats/database.py` - persisted per-order counters
  (`modification_counts` table, atomic UPSERT ... RETURNING reservation,
  budget reset when `update_order_status` reaches a terminal status,
  `Rule7StateError` fail-closed on every DB error path).
- `src/loats/rules.py` - `reserve_modification` (increment-before-broker,
  refuses past `settings.max_modifications`), `release_modification`
  (refund on broker failure), `check_modification_limit`.
- `src/loats/openalgo.py::modify_order` - the gate fires at the API
  boundary (kill switch -> payload -> reserve -> broker call; release on
  any broker/circuit failure), so every caller is gated.
- `src/loats/orchestrator.py` trailing driver - routes through the gated
  client boundary; its per-cycle cap is a documented secondary guard.
- `tests/test_rule7_modification_limit.py` - suite-level acceptance.

What was MISSING at HEAD was the verification-and-closure layer every other
closed finding carries: no external verifier, no closure record, and the
inherited readiness chains therefore (correctly, per the F8-C-01 lesson in
`docs/adr/0006`) continued to list the finding as open.

**Remediated this wave:**

- `scripts/verify_f8h02_external.py` (NEW) - outcome-scoped external
  verifier, 7 checks from a clean process: (1) counter persistence across a
  full Database teardown/rebuild, (2) reserve-before-broker caps at the
  limit with no over-issue, (3) the boundary gate fires at
  `OpenAlgoClient.modify_order` BEFORE any broker call (broker breaker
  instrumented to fail the test if reached), (4) fail-closed refusal on a
  broken counter store, (5) broker failure refunds the reserved slot,
  (6) terminal status grants a fresh budget, (7) mutation net - on a
  snapshot tree whose `modify_order` no longer reserves budget, THIS
  verifier fails on check 3, proving it verifies behavior, not idioms.
- `tests/test_repo_hygiene.py` - `TestF8H02ExternalVerifier`: GREEN
  direction (verifier exits 0 on the live tree) and RED direction (verifier
  fails on a gate-stripped snapshot), wired in-suite so the verifier cannot
  rot.

**Live evidence (HEAD, this session):** verifier 7/7 PASS; full suite
1591 passed / 0 failed, aggregate coverage 87.39%, per-module floors PASSED
(CI-exact invocations); ruff/ruff format/isort/flake8/mypy strict/bandit/
pip-audit (ADR-0010 waiver)/gitleaks all exit 0.

## Part 2 - P5 evidence-stream contamination: FIXED + GUARDED

**Defect discovered:** running the external-verifier sweep dropped
`reports/p5_forward_test_20260908_101820.json` - a closed dry-run stub -
into the production P5 evidence stream. Root cause:
`scripts/verify_f8h01_external.py::check_e_runner_validator` shells
`run_p5_forward_test.py --dry-run` without `P5_RUN_LOG_DIR`, so the runner's
default (`REPO_ROOT / reports`) applied. The stub was invisible to git
(`reports/*.json` ignored) and to the tracked-set guard; it was correctly
IGNORED by the resume selector (`dry_run: true` refusal, per the 08Sep
resume-guard wave) and carried `ended_at` (closed), so no operational
harm occurred - but the stream must stay free of machine-local debris
(the same class the 08Sep wave de-fouled: ~200 accumulated stubs).

**Fix:** check_e now pins `P5_RUN_LOG_DIR` to
`reports/health/p5-verify-stubs/` for its subprocess, mirroring the
test-suite isolation pin in `tests/test_f8h01_fixes.py`.

**Guard (class-level, disk-state aware):**
`scripts/check_repo_hygiene.py` gained `_p5_dry_run_stubs()` - a disk probe
of `reports/` for files matching the runner's dry-run stub grammar
(`metadata.dry_run is true`, `phase_gate == "P5"`, the runner script path).
Live supervised logs (`dry_run` false) are never flagged, so the gate can
never block a real run. The stub class now fails hygiene RED on disk and
GREEN after deletion - both directions exercised live this session.
Suite net: `TestF8H01VerifierEvidenceStreamIsolation` (verifier source pins
the env var; a verifier run leaves `reports/p5_forward_test_*.json`
unchanged; the guard probe flags stubs and spares live logs).

## Verifier wiring note

`scripts/verify_f8h02_external.py` is cited by `tests/test_repo_hygiene.py`
(live citation root), satisfying the scripts-wiring liveness contract; it
writes no artifacts (print-only), so it cannot re-foul the tree the way the
H-01 verifier's tracked-JSON self-churn does.
