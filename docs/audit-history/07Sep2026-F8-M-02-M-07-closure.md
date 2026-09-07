# F8-M-02 … F8-M-07 Closure Record

**Date:** 2026-09-07 · **Scope:** `docs/audit-history/01Sep2026-FR.md` §3 Medium
findings F8-M-02 through F8-M-07 (risk matrix "13.1") · **Verdict:** all six
rows CLOSED at HEAD, each backed by outcome-level evidence.

## Method

Repository evidence over narrative: every finding was re-established
against the live tree first (the audit text predates several remediation
waves), then closed only where an outcome-level verifier — not a code
reading — proves the contract holds at HEAD.

## Per-finding disposition

| Finding | Disposition | Outcome evidence |
| --- | --- | --- |
| F8-M-02 timeout cancel-list omits volatility task | REMEDIATED (ADR-0007, amended) | Behavioral: a REAL cycle run against a hung volatility producer ends it CANCELLED within the cycle on both the timeout path and the producer-raises path; settle wired at both boundaries. Unit net: `tests/test_orchestrator_extra.py::TestProducerWindowLifecycle`. |
| F8-M-03 checks verify idioms not outcomes; HC-26 Win32 blind spot | REMEDIATED | `strength.py` states the behavioral bare-env contract (no "scanner evasion" rationale); HC-15 asserts the production emission set (mutation net `TestHC15MutationNet` proves FAIL direction); HC-26 uses `os.scandir` membership via the shared `win32_root_junk` helper — a `G......` fixture is detected (previously invisible to `Path.exists()`); bare-env import probe runs in-suite. |
| F8-M-04 root junk `G......` | REMEDIATED | Live root enumeration (`os.scandir`) holds no pinned junk name and no Win32-hostile class name; the class-wide detector is wired into `check_repo_hygiene.py` (`root_junk_findings`), so the NEXT shell-redirection mishap fails regardless of its name. |
| F8-M-05 report/run-artifact sprawl | REMEDIATED | `git ls-files reports/` top level holds exactly the five evidence-of-record artifacts named in `check_repo_hygiene.py` ALLOWLIST; run artifacts are gitignored (`reports/*.json`, `reports/health/run*.json`) per ADR-0011. |
| F8-M-06 `.env.test` tracked | REMEDIATED | `git ls-files -- .env*` returns only `.env.example`; the hygiene guard forbids `.env.test` by pattern; test env is sourced from `tests/conftest.py`. |
| F8-M-07 VIX threshold inline | REMEDIATED | `vix_gate_threshold: float = 15.0` lives in `config/settings.py` (CMP Rule 10 comment); `rules.py::check_vix_gate` reads the setting with no inline `> 15` / `< 15` literal; behavioral: BUY passes at 14.9, SELL at 15.1, unknown VIX blocks both (block_all fail-safe). |

Low rows verified in passing: F8-L-04 probe debris absent from HEAD
ancestry; F8-L-05 RSS validator wired (CI offline job + live startup
gate). F8-L-01/L-02 remain carried P3 backlog by design; F8-L-03/L-06
are documented limitations.

## External verifier

`scripts/verify_f8m02_m07_external.py` runs from a clean process
(no test fixtures, no mocks of the system under test) and exits 0 iff
all 19 outcome checks pass. Honest-machine proof (2026-09-07,
CPython 3.12, Windows 11):

* GREEN: unmutated snapshot → `VERIFIED: 19/19`, rc=0.
* RED: snapshot with `await _settle_cancelled_producers(producers)`
  removed from both cycle boundaries → rc=1,
  `[FAIL] m02c_settle_wired_on_both_boundaries found 0 settle call
  sites, need exactly 2`.

The RED/GREEN pair is re-proven on every pytest run by
`tests/test_repo_hygiene.py::TestF8M02M07ExternalVerifier` (live-tree
GREEN + snapshot-mutation RED), so the verifier cannot silently rot
into an idiom checker — the exact erosion class F8-M-03 flagged.

## Operational note (Win32)

The verifier's trailing-dot fixture must be deleted through the
extended-length path (`\\?\...`); a normal-path delete cannot address
the name, and `TemporaryDirectory.cleanup()` then fails with WinError
145 — the same hostile property HC-26 exists to detect. The fixture
removes itself in a `finally` block.
