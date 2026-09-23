# 23Sep2026 — Orphaned fixer-hook mutant sweep: incident record and recovery protocol

Classification: test-infrastructure incident (process kill), no product-code
defect. Status: RECOVERED same day; prevention candidates recorded, decision
deliberately open (not one-key). Companion field lessons live in the
engineering skill references (Class 5, concurrent-suite failure classes).

## 1. Summary

During the 23Sep chunked full-suite verification at `7e124c3`, a hard process
kill (foreground timeout window) landed while
`tests/test_repo_hygiene.py::TestFixerHooksSpareFrozenEvidence` was running.
The test's child — `pre_commit run --config pre-commit-no-excludes.yaml
trailing-whitespace|end-of-file-fixer --all-files`, the excludes-stripped
MUTANT config — was orphaned and kept rewriting the frozen evidence trees
(`docs/audit-history/`, `reports/ai-generated/`). The test's `finally` repair
never fired because the parent was TerminateProcess'd. Result: 87 frozen
files left ` M` (whitespace-only, EOF-newline diffs).

## 2. Why the poisoned state compounds (the order-dependence mirage)

Every later run's damage-delta (`_dirty_paths()` after − before) came back
EMPTY: the files were already ` M` at session start, so the mutant test
false-REDD'd ("nothing was rewritten") and no repair happened. The symptom
looked like test order-dependence; the actual state was pre-damaged frozen
trees. Nothing in the suite distinguishes "mutant rewrote nothing" from
"mutant's work is indistinguishable from pre-existing damage" — that
observability gap is the defect class.

## 3. Detection signature

- `git status --porcelain`: ~87 ` M` entries CONFINED to the frozen trees.
- `git diff` per file: balanced insertions/deletions, whitespace-only
  (EOF-newline class).
- A hygiene/mutant test failing "Right contains 1 more item"-style while a
  sibling session was killed mid-run.

## 4. Recovery protocol (verified 23Sep)

1. Verify frozen-confinement AND whitespace-only diffs (both, always).
2. `git checkout -- docs/audit-history/ reports/ai-generated/`
3. Run `TestFixerHooksSpareFrozenEvidence` solo: must PASS and leave
   `git status --porcelain` empty (dirty=0).
4. Re-run the affected chunks; treat any coverage verdict from data merged
   across the kill as void (§5).

## 5. Coverage corollary (killed `--cov` runs poison later merges)

TerminateProcess skips coverage's atexit flush: a killed `--cov` run leaves
holes in later `--cov-append` merges and can floor-FAIL modules that are
actually healthy. Measured 23Sep: `alerts.py` 18.3% and `backtest_sanity.py`
25.3% from merged data were artifacts — single-process re-measure 88% / 86%,
CI green on the same SHA. Rule: never trust a coverage/floor verdict from
merged data that includes a killed run; re-measure suspect modules
single-process; the CI pipeline verdict on the same SHA is authoritative.

## 6. Companion sizing trap (kill misattribution)

A 130s `timeout` guard false-wedges the pre-commit-subprocess tests (~3 min
is LEGITIMATE; chunk_0700 needed 187s). An F in a timed-out chunk may be
THIS class: check frozen-tree damage via `git status` BEFORE hunting
session-state leaks or diagnosing a code defect.

## 7. Prevention candidates (OPEN — decision deliberately deferred)

- (a) Process-tree kill: suite timeouts kill the whole tree
  (`taskkill /PID <pid> /T /F`), so no hook child can outlive its parent.
- (b) Pre-run frozen-tree guard: `TestFixerHooksSpareFrozenEvidence` (or
  conftest) fails closed when the frozen trees are already dirty at session
  start, converting the silent damage-delta void into a visible RED.

Both are recorded as candidates; neither is one-key safe mid-span (the
guard changes a pinned hygiene test's contract; the kill change touches the
shared push-window etiquette). Decision rides the next ops-review window.

## 8. Verification evidence (post-recovery canonical green, 23Sep2026)

Single-process full suite at `7e124c3`: **2,162 passed / 1 skipped /
0 failed, 89.48% branch coverage, 534 s, rc=0** — the authoritative
post-recovery state. The CI pipeline run on the same SHA agrees.
