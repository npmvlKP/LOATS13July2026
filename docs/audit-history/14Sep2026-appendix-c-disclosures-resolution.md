# Appendix C Resolution — "Not enough evidence" Disclosures Re-verified

**Date:** 2026-09-14 (Asia/Calcutta). **Live HEAD:** `3dfb9c0`
(`origin/main` == local `main`, CI run 34825807683 green).
**Supersedes:** Appendix C of `01Sep2026-FR.md` (authored 2026-09-01 at a
pre-probe-cleanup HEAD). That document is frozen evidence and is
intentionally left untouched; this record is the current disposition of
record for its six disclosures.

## Method

Repository evidence over narrative: every resolution below was re-verified
by live execution at `3dfb9c0` (Windows 11, `loatsNEW` venv, Python 3.12.7)
— authenticated GitHub API read-backs, workflow run reads, the repo's own
external verifiers, tracked-artifact JSON reads, and git object reads.

## Disposition table

| Appendix C item (01Sep) | 01Sep verdict | 14Sep verdict | Live evidence at `3dfb9c0` |
| --- | --- | --- | --- |
| Branch protection on `main` (TODO-5b) | Not enough evidence (UI) | RESOLVED | See (1) below |
| OpenAlgo server-side `Idempotency-Key` honoring | carried | CARRIED (environmental) | See (2) below |
| P1 "live" latency | analysis-scope only | RESOLVED (F8-L-03) | See (3) below |
| CMP chain under real multi-source feeds | unobservable (3 sources vs gate 4) | RESOLVED (F8-C-01) | See (4) below |
| P5 2-week forward test | not begun | BLOCKED (unchanged, by design) | See (5) below |
| `security.yml` weekly workflow executions | runs not inspected | RESOLVED | See (6) below |

## Item detail

1. **Branch protection on `main` (TODO-5b) — RESOLVED.** The probe commit
   `44f91515` is absent from this clone: `git cat-file -e 44f91515` exits
   128 (object never fetched after the F8-L-04 cleanup; also absent from
   `git log --all` and the reflog), and `0576eb36` is equally
   unresolvable. Local `main` and `origin/main` both sit at `3dfb9c0`
   (ahead/behind 0/0) — a clean, fully synced tree. Server-side rules
   ARE inspectable from this environment: an authenticated
   `gh api repos/npmvlKP/LOATS13July2026/branches/main/protection` GET
   (2026-09-14) returns `required_approving_review_count=1`,
   `strict=true`, `enforce_admins.enabled=true`, 10 required contexts
   (`isort`, `flake8`, `bandit`, `deps-sync`, `ruff-lint`,
   `ruff-format`, `commit-lint`, `mypy`, `pytest-coverage`, `pip-audit`),
   `required_conversation_resolution=false`, `restrictions=null`. The
   01Sep "not inspectable from the repository" premise is superseded by
   this successful read. Empirical enforcement stands (CONTRIBUTING.md
   §Setup 4): a direct force-push to `main` was rejected GH006
   "Protected branch update failed" on 2026-09-04.
   `scripts/verify_carried_set_external.py` probe-debris checks PASS
   (both SHAs unresolvable; F8-L-04 DISCHARGED with server-side proof) —
   31/31 overall at this HEAD.

2. **OpenAlgo server-side `Idempotency-Key` honoring — CARRIED, scope
   bounded.** Still not verifiable from this repository: honoring
   behavior lives in the OpenAlgo server codebase/logs, outside repo
   evidence. The client-side contract is closed and verified
   (`verify_carried_set_external.py` broker-idempotency block: 2 header
   sites, get-or-create TTL key helper, database dedupe on the
   `store_order` path, behavioral key-stability probe). Defense in depth
   is unchanged: the no-retry circuit breaker on order placement remains
   the primary duplicate-order control and the `openalgo.py` module note
   (line 31) is current. This is an environmental verification item, not
   repository debt.

3. **P1 "live" latency — RESOLVED by F8-L-03 (closed 2026-09-03).** The
   01Sep disclosure described the single-scope artifact class. The
   tracked canonical artifact
   `reports/p1_analyze_latency_20260904_040609.json` carries
   `fix_version: "3.0 - F8-L-03: two-scope evidence"`,
   `measurement_scope: "live-endpoint"`, `p1_discharging: true`, commit
   `e6c2da34`. Its `live_evidence` scope records 100 real
   `POST /api/v1/quotes` HTTP round trips to the configured OpenAlgo
   endpoint with the quotes cache bypassed before every sample:
   mean 57.62 ms, p95 74.05 ms, max 53.05 ms p99 (in-process scope:
   mean 10.44 ms), against a 100 ms round-trip gate — 100/100 gate
   compliance, 90/100 all-gates (the db scope's 20 ms gate absorbs the
   10 slowest local writes by design). The verifier's P1 block re-passed
   live at this HEAD (artifact tracked at the canonical path; scope
   live-endpoint and P1-discharging).

4. **CMP chain under real multi-source feeds — RESOLVED by F8-C-01 Wave 2
   (closed 2026-09-08).** The disclosure's premise ("production produces
   3 sources; the diversity gate requires 4") is stale: production now
   emits **5 of 7** sources — `TECHNICAL_ANALYSIS`, `SENTIMENT`,
   `VOLATILITY`, `PRICE_ACTION`, plus the 5th real producer
   `OPTIONS_FLOW` (put/call volume flow + IV skew from the nearest-expiry
   chain via `get_option_chain`; `FUNDAMENTAL`/`MACHINE_LEARNING` were
   evaluated and rejected as would-be fabricated diversity).
   `scripts/verify_f8c01_external.py` re-ran 7/7 PASS live at this HEAD:
   5 distinct emission sites; gate arithmetic 3-src rejected
   (0.4286 < 0.5); a live `price_action` producer stored a real signal;
   the full five-producer cycle stored a 5-source set passing
   `validate_signal_sources` at diversity 0.7143 (single-outage
   redundancy: one breaker trip leaves 4/7 = 0.5714 >= 0.5); a complete
   `TradeDecision` persisted (status PENDING, strength 0.6260); and the
   mutation-safety probe failed closed on a mutated copy. Residual
   observability under genuinely live multi-source broker feeds is
   subsumed by the P5 supervised run (item 5), not carried separately.

5. **P5 2-week forward test — BLOCKED, unchanged, by documented design.**
   Correctly still not begun: no `reports/p5_forward_test_*.json` run log
   exists (the pattern is git-ignored runtime evidence by design, graded
   by `scripts/verify_p5_forward_test.py`). ADR-006 records the
   deliberate deviation: `analyzer_routing_enabled` stays default-OFF as
   the runtime kill path (the mandated anti-fabrication stance from
   TODO-13/HC-19), so the unconditional P5 wording cannot be satisfied
   until a supervised run enables routing. The closing step exists and is
   runnable: `scripts/run_p5_forward_test.py` (supervisor;
   `--ack-live-endpoint` required for live runs) appends a run log, and
   the verifier grades >= 14-day span, zero unhandled exceptions, routing
   enabled. The blocking condition is a documented decision awaiting
   operations scheduling, not missing implementation.

6. **`security.yml` weekly workflow executions — RESOLVED.** The weekly
   cron is present (`30 21 * * 0` — Sunday 03:00 IST) and demonstrably
   fires: scheduled run 34789490230 (`event: schedule`,
   2026-09-13T23:21:54Z, branch `main`) concluded `success` with all five
   jobs green (Code Security Analysis, Dependency Vulnerabilities, Secret
   Scanning, SBOM Generation, Security Scan Summary) and the expected
   artifacts uploaded (gitleaks SARIF, SBOM, pip-audit report, code
   security reports). Its single annotation — SBOM retention clamped to
   the repository maximum — was fixed after that run by commit `2233200`
   (2026-09-14, `retention-days: 90` cap + pinning test
   `test_security_yml_retention_days_within_repository_cap`); the
   post-fix dispatch run 34810343385 completes with zero annotations.

## Net correction

01Sep Appendix C: 6 disclosures with insufficient evidence.
14Sep: **4 RESOLVED** with live execution evidence, **2 carried by
design** — one environmental (OpenAlgo server-side idempotency, bounded
by client-side closure plus the no-retry breaker) and one operationally
blocked (P5, with the exit path scripted and documented in ADR-006).
Zero items remain in the "not enough evidence" state for anything
decidable from the repository.
