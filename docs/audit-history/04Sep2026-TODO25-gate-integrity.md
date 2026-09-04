# TODO-25 gate-integrity corrections — 04Sep2026 (F8 wave)

Follow-up to the Performance Review of 01Sep2026-FR.md §5. Four defects were
found in the P1 evidence gate chain, each verified with an adversarial
artifact or a live-tree run before fixing (RED/GREEN in
`tests/test_todo25_verifier_gates.py`).

## 1. Wrong-scope numeric gating in `verify_todo25_external.py` (P1)

The verifier required `measurement_scope: live-endpoint` (the F8-L-03 rule)
but then read mean / P95 / pass-rate from the **analysis-scope** blocks.
Proven: a synthetic artifact with a healthy in-process scope and a
catastrophic live scope (mean 480 ms, pass rate 22%) produced
"VERIFICATION: PASSED", exit 0, printing the in-process mean (10.44 ms)
next to a PASS verdict. A dead-slow endpoint could discharge P1.

Fix: when the scope is live, every numeric verdict is taken from the
`live_evidence` block, and a new check recomputes the live mean and pass
rate from the per-sample `measurements` list and requires agreement with
the summary (±0.51 tolerance; the collector rounds to 2 decimals).
Analysis-scope-only artifacts keep failing the scope check unchanged.

## 2. Vacuous `--only` selection in `fr7_health_check.py` (P1)

`--only HC-29` after the HC-29 block's deletion printed
"HEALTH SUMMARY: 0 PASS / 0 FAIL / 0 SKIP" and exited 0. A selection that
matches zero checks is indistinguishable from a passing one and is exactly
what masked defect 3. Fix: an `--only` value containing no known check id
now prints an error and exits 2.

## 3. HC-29 silently deleted from `fr7_health_check.py` (P1)

Commit `b46f4c5` (TODO-28 mypy strict sweep) removed the HC-29 catalogue
entry while rewriting the script; no gate noticed because of defect 2, and
`verify_todo25_final.py` Stage 6 (which greps for the marker) failed on
every run — including genuine evidence. Fix: HC-29 is restored as
`probe_hc29` (runs the external verifier out-of-process, like HC-28) and
wired into the `--only` dispatcher.

## 4. Tracked-file ratchets out of lockstep (P2, pre-existing at HEAD)

Commit `c34adb5` re-pinned `check_repo_hygiene.py` 416 → 426 but left
`verify_f8c02_external.py` and both TODO-21 verifiers at 416, so
`verify_f8c02_external.py` (11/12, exit 1) and
`verify_todo21_root_cleanup.py` (1 failed, exit 1) failed on a clean tree.
`verify_todo21_external.py` masked its identical stale pin behind a
non-strict `failed_checks <= 1 → PASS` leniency branch. Fix: all four
surfaces re-pinned to 428 (+2: this note and the regression test file) and
a lockstep regression test added. The leniency branch is TODO-21 legacy and
is left untouched here; its masking behaviour is now covered by the
lockstep test.

## Corrections to frozen audit prose (03/04Sep2026)

- `01Sep2026-FR.md` §5 cited the SQLite lock fix as `8306345e`; no such
  commit exists in this repository (any branch). The fix that introduced
  `PRAGMA busy_timeout=30000` is `138d376` (G01/G02, 2026-08-31). Corrected
  in place below per the frozen-dir contract (promotion documented here).
- The same table's "Latency evidence 🟡" row predates the genuine discharge
  in `80a60b7` (100/100 live TCS round trips, median 55.72 ms, max 88.20 ms,
  zero errors, `p1_analyze_latency_20260904_040609.json` live scope) and is
  annotated accordingly.

## Verification evidence (Windows, loatsNEW venv, 2026-09-04)

See the wave report; all gates re-run green after these fixes, including
the adversarial artifact now failing (exit 1) in both verifiers.
