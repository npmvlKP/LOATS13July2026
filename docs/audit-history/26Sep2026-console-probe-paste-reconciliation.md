# 26Sep2026 Paste Reconciliation — Console-Probe Tail (isort charmap Warnings, PR #87 Tail, PowerShell Redirect Error)

- **Issue ID:** 26Sep console-probe paste reconciliation · **Category:**
  Console-encoding artifact / probe normalization · **Confidence:**
  Certain (reproduction probes run live at HEAD `d486f75`).
- **Status:** RECORD ONLY — no production code changed by this wave. The
  pasted isort run is GATE-GREEN in both console environments; the
  remaining paste blocks are already-dispositioned or already-merged
  items, reconciled below. No new RISK-REGISTER row; R-01/R-05/R-07/R-08
  and R-12 remain the standing open items with their registered due
  dates.
- **Snapshot identity:** HEAD `d486f75` (PR #87 merged 2026-09-26),
  clean tree, local `main` == `origin/main`. Main CI run `36257907490`
  green at HEAD. Protection live-read (23:22–23:26 IST): strict=true,
  exactly 10 required contexts (isort, flake8, bandit, deps-sync,
  ruff-lint, ruff-format, commit-lint, mypy, pytest-coverage, pip-audit),
  `dismiss_stale_reviews: true`, `required_approving_review_count: 1`,
  admins enforced, no force-push/deletions — 8th consecutive clean
  field-by-field watch per CONTRIBUTING.md's pinned contract, and the
  first watch where the derive-gap repair was NOT needed (the 25/26Sep
  `dismiss_stale_reviews` derive gap did NOT recur). P5 run
  `reports/p5_forward_test_20260924_080208.json` LIVE during probes
  (mtime 23:26 IST, `ended_at: null` = correct in-progress state);
  `routed_decisions: 0` — the R-12 decisional-leg deadline governs
  (2026-10-08), unchanged.

## 1. Verdict table (paste claim vs live evidence)

| # | Paste claim | Live evidence at HEAD `d486f75` | Verdict |
|---|---|---|---|
| 1 | isort charmap warnings on 26 files (`Unable to parse ... 'charmap' codec can't encode ...`) | Probe re-run at HEAD on the canonical venv, CI-exact scope: under this shell's UTF-8 console (PYTHONUTF8=1, PYTHONIOENCODING=utf-8) → rc=0, zero warnings; under a forced legacy console (`PYTHONUTF8=0 PYTHONIOENCODING=cp1252`, same command) → rc=0, exactly **26** warnings matching the paste's list (see §2) | PROBE ARTIFACT — gate-green in both console environments |
| 2 | pip-audit: `Found 1 known vulnerability ... nltk 3.10.3 PYSEC-2026-3740` | The CI pip-audit job pins `--ignore-vuln PYSEC-2026-3740` (ci.yml:323, job at ci.yml:297-330) per ADR-0010's accepted-monitor disposition; safety runs clean. The pasted invocation (`python -m pip_audit` on the raw venv, no ignore leg, plus the PIPAPI_PYTHON_LOCATION warning from the dual-venv console) is the local raw form, not the CI-exact form | STALE-CLASS PROBE ARTIFACT — CI-exact invocation green; ADR-0010 monitor stands (R-05 shared-venv rebuild due 01Oct) |
| 3 | fumbled `gh pr create --head ... --base main ...` + usage dump | PR #87 MERGED at 2026-09-26T17:07:35Z, merge commit `d486f75`, main CI `36257907490` green. The paste's `# → PR #87` annotation is the prior session's tail — the PR was opened and merged before this session started | ALREADY MERGED — no action |
| 4 | `git diff a4f94db origin/main -- <changed paths>` (PowerShell parse error on the literal `<changed paths>`) | The attempted content check, completed live: `git diff a4f94db origin/main --stat` = empty — PR #87's merge commit is content-identical to `a4f94db` | ALREADY VERIFIED — content check complete |
| 5 | Log block (Strategy Module DB init, Order-update WS, option-chain/quote fetch, "full" Zerodha response dump) | Host-layer attribution: all four signatures (`Initializing Strategy Module DB`, `Order-update WS connected`, `Requesting quotes for`, `Full Zerodha response`) grep ZERO hits in LOATS `src/` — they are OpenAlgo host-checkout emitters (`G:/.OA/OpenAlgo`: `database/strategy_module_db.py`, `websocket_proxy/order_adapter.py`, `broker/zerodha/api/data.py`). The zerodha quote logger slices `data.keys()[:10]` and dumps the response `[:1000]` BY DESIGN (`data.py:373-374`): the paste showing 10 data keys for 276 instruments is log FORMATTING, not a partial API response | HOST-LAYER ATTRIBUTION — not a LOATS finding |
| 6 | Performance Review table (8 rows incl. F9-H-02 / F9-L-01 / F9-L-02 flags) | Already reconciled same-day by PR #86/#87: `26Sep2026-performance-review-paste-reconciliation.md` dispositions every flagged row (advisory-by-design gate, S-14/S-15 riders) and re-verifies the six clean rows; its mechanism citations spot-verified at this HEAD (orchestrator.py:758/902/1045/1217/1369 producer constants; strike_selection.py:219 warn-only 5 ms; orchestrator.py:2188 trail budget; settings.py:128-141 producer window + trailing-stop default; database.py:107-111 WAL + busy_timeout) | ALREADY RECONCILED — same-day record stands |

## 2. The isort charmap class — proven console-cosmetic (new pin)

The pasted warnings (26 files, `Unable to parse ... 'charmap' codec`)
did not reproduce on the canonical repo venv under the UTF-8 console
this session runs (PYTHONUTF8=1, PYTHONIOENCODING=utf-8). To attribute
them, the probe was re-run under a forced legacy console:

```
PYTHONUTF8=0 PYTHONIOENCODING=cp1252 ./.venv/Scripts/python.exe \
  -m isort --check-only src tests scripts
```

Result: rc=0, exactly 26 warnings — the paste's list (src/loats/alerts.py;
tests/test_alerts.py, test_audit_dual_write.py, test_backtest_sanity_production.py,
test_cache_additional.py, test_html_escaping_final.py, test_metrics.py,
test_p5_forward_test.py, test_payload_builder.py, test_performance_benchmarks.py,
test_per_source_breakers.py, test_repo_hygiene.py, test_sentiment_coverage.py,
test_ta.py, test_vix_integration.py; scripts/check_env_settings_sync.py,
check_function_size.py, collect_p1_phase_gate_evidence.py, commit_message_check.py,
probe_hc15_strength_gate.py, ratchet_baseline.py, run_p5_forward_test.py,
verify_todo21_external.py, verify_todo21_root_cleanup.py, verify_todo25_external.py,
verify_todo25_final.py). The characters flagged are content glyphs in
docstrings/comments (em-dash, ✓, ❌, 🚀, μ, ≈, →, ≤) — isort still parses
the AST and exits 0; the gate verdict is IDENTICAL in both console
environments. Noise-free path: any console with `PYTHONUTF8=1` (CI
runners have UTF-8 natively) prints zero warnings.

Root-cause chain: on Windows, isort's file reader falls back to the
console-inherited default encoding (cp1252) when a source file carries no
BOM/encoding declaration; UTF-8 glyph bytes then fail the cp1252 decoder
and isort prints the `Unable to parse file` warning while continuing.
Repo context: `pyproject.toml:232-242` already pins the REPO-ROOT sweep
variant of this class (venv descent + charmap warnings; `skip_gitignore
= true`, `extend_skip = ["loatsNEW"]`, CI-exact scope guarded by
`tests/test_repo_hygiene.py::TestIsortScopeImmunity`). What was not
previously pinned is the CONSOLE side of the same class: warning
visibility is console-encoding-dependent; the gate verdict is not.
Operator guidance: run local isort as
`python -X utf8 -m isort --check-only src tests scripts` (or set
`PYTHONUTF8=1` in the profile) — do NOT treat the cp1252-console
warnings as parse failures and do NOT strip glyphs from source files to
silence them.

## 3. Recommended Next Step (unchanged by this paste)

The 2026-09-30 checkpoint wave (R-01) remains the next major work: decide
ADR-0016 option (a) vs (b) citing the 25Sep evidence pack, land the S-14
(FIVE producer surfaces 758/902/1045/1217/1369, one commit) and S-15
SL-M-fixture riders, rename the ci.yml `benchmark-perf` context BEFORE
the 11-context protection PUT, promote it to required, and extend
`test_p1_items_carry_the_checkpoint_due_date` in the same commit. R-12's
decisional leg (routed_decisions=0 deep into the live span, 08Oct close)
and the R-05 shared-venv rebuild (01Oct) follow on their registered
dates.

## 4. Live-system observations during probes

- P5 span LIVE (mtime 23:26 IST, ended_at null). Kill-switch event
  already verified in-run (26Sep 12:39Z, per the same-day record).
  `routed_decisions: 0` — R-12 accumulation deficit continues; the 30Sep
  decision (record FAIL-closed evidence vs successor span) governs the
  08Oct close.
- Protection: 8th consecutive clean field-by-field read-back; first
  watch with NO derive-gap repair needed (the 25/26Sep
  `dismiss_stale_reviews` derive gap did not recur in the live config).
- Both venvs (`.venv` canonical + `loatsNEW` shared) run isort 9.0.1;
  both grade the CI-exact scope rc=0.
- This shell exports PYTHONUTF8=1 / PYTHONIOENCODING=utf-8; the paste
  originated from a cp1252 console (the `loatsNEW` PowerShell session).
  Gate verdict identical (rc=0) in both.
