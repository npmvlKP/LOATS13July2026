# Standing-Risk Discharge Wave — R1..R4 (2026-09-12)

**Date:** 2026-09-12 (Asia/Calcutta). **Base:** `main` @ `288a6bf`
(merge of PR #22, logging double-render fix). **Tree before wave:** clean,
407/407 tracked files. This record discharges the four standing risks
handed forward by the P2 closure (R1–R4): one re-verified with live
evidence (R1), one verified at HEAD and root-caused to a real gate defect
(R2→defect fixed), one held exact with a net-zero accounting (R3), and
one mitigated at every named surface (R4).

## R1 — nltk 3.10.3 / PYSEC-2026-3740 waiver currency: RE-CHECKED, WAIVER RETAINED

ADR-0010 names two removal triggers. Both verified UNLIFTED against live
sources on 2026-09-12:

* PyPI JSON API (`https://pypi.org/pypi/nltk/json`): latest release is
  still **3.10.3** — no 3.11, no patched 3.10.x.
* PyPI JSON API (`https://pypi.org/pypi/safety/json`) and the installed
  tree: latest safety is **3.8.1**, still declaring `nltk>=3.9`; the
  environment runs safety 3.8.1 + nltk 3.10.3 (importlib.metadata).

Live full-environment audit (repo venv, 128 packages audited):

```
python -m pip_audit --format=json -o .git/r1_evidence/pip_audit_raw.json
  -> RAW_RC=1, "Found 1 known vulnerability in 1 package",
     sole finding: nltk 3.10.3 / PYSEC-2026-3740 (fix_versions: [])
python -m pip_audit --format=json -o .git/r1_evidence/pip_audit_waived.json \
  --ignore-vuln PYSEC-2026-3740
  -> WAIVED_RC=0, "No known vulnerabilities found, 1 ignored"
```

Disposition: waiver remains required and current. Evidence recorded as an
ADR-0010 "Currency re-check (2026-09-12)" addendum; the four-surface
lockstep (pre-push hook, ci.yml, security.yml, HC-11) and the currency
pin (`tests/test_format_surface_contract.py::TestAdvisoryWaiverSurfaceLockstep`)
are unchanged and green.

## R2 — thin floor margins: VERIFIED PASS AT HEAD + ROOT-CAUSE FIX

Fresh HEAD-gate evidence (2026-09-12, venv-first on PATH, stale
`.coverage*`/`.mypy_cache` purged first):

```
pytest tests/ --cov=src --cov-branch --cov-fail-under=80 \
  --cov-report=xml --cov-report=term-missing \
  --cov-report=json:coverage.json --junitxml=pytest-report.xml
  -> 1777 passed, aggregate 88.21%, rc=0
python scripts/check_per_module_coverage.py
  -> all floor-mapped modules PASS, rc=0
```

Exact branch-aware margins (fresh `coverage.json`, path-keyed):

| module                        | measured | floor | margin |
|-------------------------------|---------:|------:|-------:|
| database_async_additions.py   |  81.78%  | 80    | +1.78  |
| database.py                   |  81.88%  | 80    | +1.88  |
| orchestrator.py               |  82.8%   | 80    | +2.8   |
| trade_decision.py             |  84.5%   | 80    | +4.5   |
| options.py                    |  95.2%   | 85    | +10.2  |

Defect found and fixed during this verification (forensic finding, not a
regression of this wave): `EXCLUDED_MODULES` in
`scripts/check_per_module_coverage.py` still carried
`database_async_additions.py` (plus the long-deleted TODO-15 junk-pattern
variants `_clean`/`_temp`), so the fallback path — which is the
AUTHORITATIVE path on every fresh CI checkout, the floor-map file being
gitignored-by-design — skipped the module **before** its 80% floor ever
applied, while the report loop printed `[PASS] ... threshold: 80.0%`.
The FR map, the pyproject contract comment and the guard test all name
that floor as authoritative; the exclusion made it dead configuration
(a silently narrowed gate with cosmetic PASS output — worse than no
floor, because it looked enforced).

Fix: exclusion list reduced to `["__init__.py"]` (package markers, never
floor-mapped, omitted from coverage measurement anyway) with the history
inline; RED-first net added in `tests/test_coverage_floor_map.py`
(`test_no_floor_mapped_module_is_also_excluded`,
`test_fallback_exclusions_cannot_void_mapped_floors`,
`test_exclusions_only_name_modules_absent_from_src`) — all three failed
on the pre-fix tree and pass post-fix. Post-fix the gate genuinely grades
the module: `[PASS] database_async_additions.py: 81.8% (threshold: 80.0%)`.

Disposition: R2 discharged — margins verified at HEAD, and the floor they
sit on is now provably enforced, not cosmetic. The pairing guidance (new
code in these modules ships with tests) remains standing practice.

## R3 — tracked-file ceiling 407/407: HELD EXACT, NET-ZERO WAVE

This wave's file accounting: +1 `docs/audit-history/12Sep2026-standing-risk-discharge.md`
(this record), −1 `docs/CONTRIBUTING.md` (stale fork removed, see R4).
Net tracked files after staging: **407 = ceiling**, zero re-pin needed,
`scripts/ratchet_baseline.py` untouched (single source,
import-pinned by `tests/test_repo_hygiene.py` and
`tests/test_todo25_verifier_gates.py`).

## R4 — coverage_floor_map.json discoverability: MITIGATED AT ALL SURFACES

* `.gitignore`: inline rationale at the rule — untracked-by-design,
  canonical map lives in `scripts/check_per_module_coverage.py`
  (`FR_FLOOR_MAP`), double-entry pinned by `tests/test_coverage_floor_map.py`;
  edit the script, never a local copy.
* `README.md`: quality-gate section now carries the CI-exact commands
  including `python scripts/check_per_module_coverage.py` (the gate that
  owns the map), so a contributor meeting the guard hits the canonical
  surfaces in one hop.
* `docs/CONTRIBUTING.md` deleted: a stale 2026-08 fork of the root
  canonical `CONTRIBUTING.md` (divergent blob, zero in-repo references,
  superseded commit-format section). Root file is the single contract;
  GitHub surfaces it from the repo root. Duplicate-surface confusion was
  the same root cause class as R4 itself.

## Adjacent correction in the same sweep

`README.md` carried stale evidence figures (89.02% / 784-of-801 tests,
pre-dating the suite's growth to 1777 tests). Replaced with the measured
values from this wave's run (88.21% / 1777 passing) and the lint command
scope was aligned to the CI ruff jobs (`src/ tests/ scripts/`), matching
`.github/workflows/ci.yml` exactly.

## Verification

* RED leg (pre-fix): `pytest tests/test_coverage_floor_map.py -q` →
  3 failed (the three new pins), 12 passed — failures name exactly the
  overlap defect.
* GREEN leg (post-fix): `pytest tests/test_coverage_floor_map.py
  tests/test_check_per_module_coverage.py tests/test_repo_hygiene.py -q`
  → **130 passed**, rc=0.
* Per-module gate at HEAD (fresh artifact): all floor-mapped modules
  PASS, rc=0 (see R2 table).
* Full suite at HEAD: 1777 passed, aggregate 88.21%, rc=0 (HC-12 class).
* pip-audit raw rc=1 / waived rc=0 with the single finding identified
  (HC-11 class, live).
