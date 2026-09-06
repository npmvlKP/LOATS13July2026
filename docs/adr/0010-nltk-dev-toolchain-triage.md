# ADR 0010: NLTK dev-toolchain vulnerability triage in the pip-audit gate (PYSEC-2026-3740)

## Status

Accepted — 2026-09-06

## Context

On 2026-09-06 the HC-11 pip-audit gate (clean tree, zero code changes)
turned red with exactly one finding:

* `PYSEC-2026-3740` — nltk `<3.11`: several model-artifact APIs treat
  caller-controlled model paths as ordinary filenames even when NLTK
  path security is enforced (path traversal on model loaders).
* Installed version: nltk 3.10.3. **No fixed release exists upstream**
  (pip-audit reports no fix version; PyPI has no nltk 3.11).

The package is **not a runtime dependency**:

* No `src/loats` module imports nltk (`grep -rn "nltk" src/` matches
  only a warning-suppression comment for newspaper4k's optional NLP
  extra in `src/loats/sentiment.py`).
* nltk enters the environment solely as a transitive dependency of
  `safety` — the dependency-audit tool itself. Every safety 3.x release
  (checked against the PyPI metadata for 3.8.0–3.8.1, the range pinned
  by `.github/workflows/security.yml`) declares `nltk>=3.9`.

Therefore the finding has zero production attack surface: the trading
runtime never imports nltk, and the vulnerable code paths (model
artifact loaders) are never exercised by the audit tool's own execution.

## Decision

1. HC-11 keeps auditing the **full environment** (strictest posture;
   HC-11 is SKIP-tolerant offline but must PASS online).
2. The single finding is explicitly waived at the gate with
   `--ignore-vuln PYSEC-2026-3740`, with the full rationale and removal
   trigger inlined in `scripts/fr7_health_check.py` at the invocation
   site — a bare ignore with no explanation would rot.
3. Removal triggers (any one lifts the ignore):
   * safety ships a release that drops the nltk dependency;
   * nltk 3.11 (or a patched 3.10.x) is published.
4. CI/`security.yml` are left WITHOUT the ignore: those jobs install
   only `pip-audit` (no safety → no nltk → nothing to waive), so adding
   it there would be dead configuration. The local full environment is
   the only place the advisory can fire.

## Consequences

* HC-11 returns to green online without weakening the audit's scope.
* The waiver is loud, single-site, self-documenting, and carries an
  explicit removal trigger — it cannot silently become permanent.
* If a *runtime* dependency ever gains an unpatched advisory, this
  decision does not apply: that remains a hard gate failure by design.
