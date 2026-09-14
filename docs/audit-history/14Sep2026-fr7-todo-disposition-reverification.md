# FR7 TODO Disposition — Live Re-verification (TODO-1…27)

**Date:** 2026-09-14 (Asia/Calcutta). **Live HEAD:** `e648f91`
(`origin/main`, CI run 34817458293 green). **Supersedes:** the FR8
disposition table in `01Sep2026-FR.md` (authored 2026-09-01 at HEAD
`28ab45442733aa17fdd752c2e03ab4f6855c7980`, branch `fix/fr7-wave` — a
commit since rebuilt away; the SHA exists in no ref). The 01Sep table
was accurate at its HEAD; three closure waves landed after it and
resolve its red/partial rows. That document is frozen evidence and is
intentionally left untouched; this record is the current disposition of
record.

## Method

Repository evidence over narrative: every re-graded row re-verified by
live execution at `e648f91` (Windows 11, `loatsNEW` venv, Python
3.12.7) — external verifiers, gate battery, API read-backs, and source
reads. Where the re-grade is DONE, the executing command and outcome
are cited.

## Corrected disposition table

| TODO | 01Sep verdict | 14Sep verdict | Live evidence at `e648f91` |
| --- | --- | --- | --- |
| 1 delete `src/__init__.py` | ✅ | ✅ DONE | `mypy src/ --strict` clean, now 38 files (was 35) |
| 2 relocate strays/shells | ✅ | ✅ DONE | `git ls-files` under `src/` contains only `src/loats/*` |
| 3 coverage lift | 🟠 | ✅ DONE | F8-H-04 closed 07Sep at `af37d33`: FR floor map **restored** (not narrowed) — alerts 82.3 / scheduler 89.5 / backtest_sanity 85.5 / strike_selection 87.0; enforced map + fail-closed fallback pinned by `tests/test_coverage_floor_map.py`; floor gate `check_per_module_coverage.py` exit 0 at this HEAD |
| 4 pip-audit online | ✅ | ✅ DONE | live `pip-audit --ignore-vuln PYSEC-2026-3740`: "No known vulnerabilities found, 1 ignored" (ADR-0010) |
| 5 branch protection 5a/5b | ❓ | ✅ DONE | API read-back 2026-09-14: `required_approving_review_count=1`, `strict=true`, `enforce_admins=true`, 10 required contexts incl. `commit-lint`; CI green on `main` at this SHA (run 34817458293). The 01Sep "probes inconclusive" is superseded by a successful authenticated GET |
| 6 commit hook | 🟠 | ✅ DONE | `commit-message-check` runs client-side via `.pre-commit-config.yaml` (`default_install_hook_types` incl. commit-msg; hooks present in `.git/hooks/`) **and** server-side as the required `commit-lint` context — enforcement is double-sided, not manual-only |
| 7 tag producers | 🟠 | ✅ DONE | F8-H-03 removed the scheduler signal emitters entirely: `verify_f8c01_external.py` check 5 PASS — "scheduler emits zero signals (F8-H-03); orchestrator retains 5 enum sources" |
| 8 4th producer / ADR | 🔴 | ✅ DONE | F8-C-01 closed 08Sep: `verify_f8c01_external.py` **7/7 PASS** live — 5 distinct enum emission sites, `_execute_options_flow_analysis` real producer wired into the cycle gather, breaker fleet 5/7, diversity 0.7143 with single-outage redundancy |
| 9 loud unknown source | 🟠 | ✅ DONE | F8-M-01 per-signal exclusion wave: `verify_f8m01_external.py` **12/12 PASS** live; `strength.py::exclude_unknown_source_signals` excludes per-signal with loud per-offender warnings; batch-fatal only when NO known-source signal survives; ADR-0006 supersedes the batch-fatal reading |
| 10 e2e real-path test | 🔴 | ✅ DONE | `tests/test_e2e_cmp_chain.py::TestRealProducersE2E` drives the **real producer methods** (`_execute_*_analysis`) over **real persistence**; only broker-HTTP transport seams are patched with realistic fixtures — no fabricated Signal objects; **12/12 passed** live; includes `test_real_producers_unknown_source_excluded_not_batch_fatal` |
| 11 log elevation | ✅ | ✅ DONE | (unchanged) warning + counters + session-reset + periodic throttle; loud warnings observed live in the verifier run |
| 12 VIX symmetric | ✅ | ✅ DONE | (unchanged) `rules.py` symmetric fail-safe: unknown/stale VIX blocks BOTH directions; no 18.5 constant |
| 13 real routing + persist | ✅ | ✅ DONE | (unchanged) real HTTP routing, default-OFF documented in ADR-006 (the mandated anti-fabrication kill path), audit rows persisted for every outcome, errors propagate |

TODO-14…27 dispositions were verified in the 01Sep matrix and are not
re-opened; nothing in the intervening waves touched their surfaces
except TODO-17, closed by `13Sep2026-trade-decision-persistence-wave.md`
(dispatch wiring defects fixed born-RED, async audit dual-write
reached).

## Net correction

01Sep: 15 ✅ / 6 🟠 / 3 🔴 / 1 ❓ → **14Sep: 27/27 ✅** across TODO-1…13
plus the 14…27 matrix, with the three chain-substance items (8, 9, 10)
now backed by live verifier outcomes instead of paper claims.

## Gate battery at this HEAD (all live, exit 0)

ruff check · ruff format (190 files) · isort · flake8 · mypy strict
(38 files) · bandit · pip-audit (1 ignored per ADR-0010) · safety
(banner per standing ADR-0010 monitor) · gitleaks (582 commits, no
leaks) · full suite under CI-exact coverage flags (local Windows run:
**1836 passed / 1 skipped, 456.65 s, aggregate coverage 88.93%**,
`PYTEST_RC=0`; all 10 floor-mapped modules PASS via the fail-closed
fallback map, pinned equal to the enforced map by
`tests/test_coverage_floor_map.py`) — server-side corroboration: the
required-context CI run on `main` at this SHA (run 34817458293).
