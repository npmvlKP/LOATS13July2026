# ADR 0010: NLTK dev-toolchain vulnerability triage in the pip-audit gate (PYSEC-2026-3740)

## Status

Accepted — 2026-09-06 (amended 2026-09-09: waiver surface lockstep;
re-affirmed 2026-09-12: live currency re-check, see the closing
section)

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
4. CI/`security.yml` also carry the ignore (amendment 2026-09-09,
   superseding the original waiver-free-CI decision of 2026-09-06):
   those jobs install no `safety` — hence no nltk — so the flag is a
   functional no-op there, but it is kept on every audit surface in
   lockstep (pre-push hook, ci.yml, security.yml, HC-11) so all
   surfaces enforce one contract. A surface missing the flag fails
   closed on this advisory while the others stay green — the
   live-verified defect class pinned by
   tests/test_format_surface_contract.py::
   TestAdvisoryWaiverSurfaceLockstep after the pre-push hook died on
   exactly this mismatch. The no-op flag on safety-free surfaces is
   accepted, documented dead weight; any future RUNTIME advisory
   still fails every surface.

## Consequences

* HC-11 returns to green online without weakening the audit's scope.
* The waiver is loud, self-documenting on every surface, and carries
  an explicit removal trigger — it cannot silently become permanent.
* If a *runtime* dependency ever gains an unpatched advisory, this
  decision does not apply: that remains a hard gate failure by design.

## Currency re-check (2026-09-12)

Both removal triggers verified UNLIFTED against live sources on
2026-09-12 (repo venv, Windows host):

* PyPI JSON API: latest nltk release is still 3.10.3 — no 3.11 and no
  patched 3.10.x exists upstream.
* PyPI JSON API and the installed tree: latest safety is still 3.8.1
  and still declares `nltk>=3.9`; the environment runs safety 3.8.1
  with nltk 3.10.3 (importlib.metadata).

Live full-environment audit re-run (128 packages audited): the raw
scan exits 1 with PYSEC-2026-3740 as the ONLY finding; the identical
scan carrying `--ignore-vuln PYSEC-2026-3740` exits 0 ("No known
vulnerabilities found, 1 ignored"). The waiver remains required and
current; the surface lockstep and the currency pin
(tests/test_format_surface_contract.py) stay as decided above.
