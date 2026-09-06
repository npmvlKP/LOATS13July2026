# ADR 0011: Security-scan artifacts under reports/security/ are run artifacts, not evidence of record

## Status

Accepted — 2026-09-06

## Context

On 2026-09-06 the `repo-hygiene` pre-commit gate rejected two files that
a `git add -A` had swept into the index:

* `reports/security/bandit.json` — a fresh local bandit scan
  (`generated_at: 2026-09-06T04:26:34Z`).
* `reports/security/safety-report.json` — safety 3.x `check --save-json`
  output whose `report_meta.scanned` paths embed machine-absolute
  Windows paths (`G:\.OA\...`).

The tracked-file ceiling (380) flagged the sweep. Investigation showed:

* CI writes its own copies at the repository root
  (`security.yml`: `bandit-full-report.json`, `safety-report.json`) and
  uploads them as run artifacts; it never reads a tracked copy.
* No script, workflow, test, or doc references the un-dated names — the
  zero-hit greps across `*.py|*.yml|*.md`.
* The evidence of record under `reports/security/` is the **dated
  snapshot** scheme (`bandit-20260901.json`,
  `pip-audit-20260901.json`), already tracked, mirroring the P1
  canonical-evidence convention in `.gitignore`.

Separately, the `commit-message-check` hook crashed while rejecting a
non-conventional message: its rejection diagnostic embedded the subject
verbatim, and the subject's `→` (U+2192) is unencodable on a cp1252
console — so the operator saw `Failed` with no reason. That defect is
fixed in `scripts/commit_message_check.py` (fail-soft `_emit` writer)
with its own regression tests; this ADR covers the hygiene decision.

## Decision

1. Un-dated security-scan output under `reports/security/` is a **run
   artifact**: re-derivable, machine-local, and not referenced by any
   gate. It is untracked and pinned in `.gitignore`
   (`reports/security/bandit.json`,
   `reports/security/safety-report.json`).
2. The evidence of record remains the **dated snapshot** scheme. A new
   canonical snapshot requires a deliberate commit naming the wave that
   produced it (same discipline as the P1 evidence negations).
3. CI's root-level tool outputs (`bandit-report.json`,
   `bandit-full-report.json`, `pip-audit-report.json`,
   `pip-audit-core-report.json`, `safety-report.json`) are likewise
   pinned in `.gitignore` so a future CI parity run or a locally
   reproduced CI step cannot re-trip the ceiling.
4. The tracked-file ceiling moves 380 → 382 (+1 regression test module
   for the commit gate, +1 this ADR; the two removals offset the adds),
   following the ADR-0009 single-source re-pin protocol.

## Consequences

* `git add -A` can no longer smuggle scan output into the index; the
  hygiene gate stays meaningful as a ratchet.
* Machine-absolute paths never enter the repository history through
  safety reports (information-leak hygiene on a shared repo).
* Re-pin protocol exercised end-to-end: lockstep tests
  (`TestRatchetSingleSource`, `TestRatchetLockstep`) assert every
  consumer resolves the new value structurally.
