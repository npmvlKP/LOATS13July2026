#!/usr/bin/env python3
"""Canonical tracked-file ratchet baseline (F8-L-07).

Single source of truth for the tracked-file ceiling. The 416-vs-426
split class: the same integer was hand-pinned in four gate scripts
(scripts/check_repo_hygiene.py, scripts/verify_f8c02_external.py,
scripts/verify_todo21_external.py, scripts/verify_todo21_root_cleanup.py);
re-pinning one surface without the others left committed gates failing
on a clean tree. Every ratchet surface now imports TRACKED_FILE_CEILING
from this module, so lockstep is structural rather than procedural.

Re-pin protocol (next wave that changes the tracked-file count):
  1. Edit TRACKED_FILE_CEILING here — the ONLY place the number lives.
  2. Update the history block below (wave ID, +/- file delta, new value).
  3. Run: pytest tests/test_repo_hygiene.py tests/test_todo25_verifier_gates.py
     TestRatchetSingleSource/TestRatchetLockstep assert every surface
     resolves to this value at runtime; a missed surface fails them.

No other constant belongs here: keep this module import-free (stdlib
only, no side effects) so every consumer can load it in any context
(CI, pre-commit, health-check subprocess, importlib spec-load).

History (most recent last):
  369  measured count at 7a2ea233^ (immediately before the TODO-25 venv
       sweep; the TODO-21 ratchet <=343 had gone stale).
  415  F8-M-02 hygiene follow-up (2026-09-03): 16 session-agent files
       untracked; tree re-measured at 411.
  416  +1 docs/audit-history/03Sep2026-F8-L-03-closure.md.
  425  F8-L-05 (2026-09-04): +9 RSS-wave files.
  426  F8-L-06 (2026-09-04): +1 F8-L-06 closure record.
  429  TODO-25 gate-integrity wave (2026-09-04): +3, then +1 F8-L-03
       discharge evidence.
  377  F8-L-06-R2 (2026-09-05): -55 (48 dead one-wave scripts + 7
       orphaned report artifacts, ADR-0008), +3 wiring-guard files.
  379  F8-L-07 (2026-09-05): +2 (this module — the ceiling's new
       home — and its decision record docs/adr/
       0009-ratchet-baseline-single-source.md; see ADR-0009).
       scripts/ orphans are separately ratcheted by
       scripts/check_scripts_wiring.py (CI repo-hygiene, pre-commit,
       HC-30).
  380  CI/security workflow flag-drift repair wave (2026-09-06):
       +1 docs/adr/0010-nltk-dev-toolchain-triage.md (PYSEC-2026-3740
       triage decision record; see ADR-0010).
  382  Commit-gate observability wave (2026-09-06): +2
       (tests/test_commit_message_check.py — regression net for the
       cp1252 rejection crash and the F8-L-06-R2 format rule — and
       docs/adr/0011-security-report-artifacts.md; see ADR-0011). The
       same wave untracked 2 accidental git-add -A sweep-ins
       (reports/security/bandit.json, reports/security/
       safety-report.json — undated scan output; they were staged but
       never committed, so no committed file was removed).
  383  CI parity wave (2026-09-06): +1
       (docs/adr/0012-ci-parity-linux-runners.md — decision record for
       the 26 GitHub-runner-only failures found by the first
       workflow_dispatch proof: editable-install contract, mypy
       platform-stub lambda, EXE001 exec bits, POSIX casefold gap,
       host-specific verifiers; see ADR-0012).
  382  DevOps workflow-integrity wave (2026-09-07): -1
       (reports/f8-h-03-verification.json — a zero-reference,
       machine-local verifier run artifact with embedded working-tree
       state and absolute paths — relocated to
       docs/audit-history/f8-h-03-verification-20260902.json per the
       ADR-0011 artifact discipline. The rename keeps the count at 382,
       so the ceiling now equals the tree: any net addition requires a
       deliberate re-pin.
  384  F8-M-02..07 closure wave (2026-09-07): +2
       (scripts/verify_f8m02_m07_external.py — the clean-process
       outcome verifier for risk-matrix rows F8-M-02..F8-M-07 — and
       docs/audit-history/07Sep2026-F8-M-02-M-07-closure.md, its
       closure record; see the record's External verifier section).
       Wired live by tests/test_repo_hygiene.py::
       TestF8M02M07ExternalVerifier.
  386  Shebang exec-bit normalizer wave (2026-09-07): +2
       (scripts/ensure_shebang_exec_bit.py — the ADR-0013 self-healing
       pre-commit normalizer for the Windows 100644 shebang class —
       and its decision record
       docs/adr/0013-shebang-exec-bit-normalizer.md).
  387  F8-H-01 forward-test integrity (2026-09-07): +1
       (tests/test_f8h01_fixes.py — regression net for the producer
       window, the validator's decisional-activity criterion, the
       P5_RUN_LOG_DIR runner isolation, and the conftest test-data
       isolation; ADR-006 Amendment 2).
  389  F8-H-01 P2 follow-up (2026-09-07): +2
       (scripts/quarantine_test_data.py — fingerprint-only quarantine
       of test-contaminated trade decisions into
       trade_decisions_quarantined, audit trail untouched; and its
       regression net tests/test_quarantine_test_data.py).
  390  ASCII gate contract wave (2026-09-07): +1
       (docs/adr/0014-src-ascii-gate-contract.md — the born-red,
       never-wired src ascii gate made enforceable: prose characters
       normalized to ASCII across src/, test-pinned alert emoji
       enumerated in the gate's ALLOWED_NON_ASCII, gate wired into the
       CI repo-hygiene job and pre-commit; see ADR-0014).
  391  F8-H-04 closure wave (2026-09-07): +1
       (docs/audit-history/07Sep2026-F8-H-04-closure.md — outcome
       evidence for the restored FR floor map at HEAD af37d33: fresh
       1553-test run, aggregate 87.33%, all ten floor-mapped modules
       green; closure record for register item 5).
  393  Carried-set reconciliation wave (2026-09-07): +2
       (docs/audit-history/07Sep2026-carried-set-reconciliation.md —
       register item 8 re-derived against the tree: seven of eight
       carried items CLOSED/DISCHARGED with pinned evidence,
       as_of_date registered as the sole open item; and
       scripts/verify_carried_set_external.py — the clean-process
       outcome verifier for those dispositions, wired live by
       tests/test_repo_hygiene.py::TestCarriedSetExternalVerifier).
  394  F8-L-02 acceptance net wave (2026-09-07): +1
       (tests/test_as_of_date_propagation.py — 11-test acceptance net
       for the caller-supplied as_of_date propagation into
       decision/audit records: model field, engine + orchestrator
       parameters, trade_decisions column round trip, CREATE/ROUTE
       audit rows, and the zero-date.today() invariant).
  395  F8-L-02 closure-record wave (2026-09-07): +1
       (docs/audit-history/07Sep2026-F8-L-02-closure.md — the closure
       record for the register's last open item, with the wave's
       implementation surfaces, behaviour contract, and acceptance
       evidence. Carried set now eight of eight CLOSED/DISCHARGED).
       [Subsequent stale-verifier removal wave (PR #10) took the tree
       back to 394; the ceiling stayed 395.]
  395  P5 resume-guard + sanity-interval wave (2026-09-08): +1
       (docs/audit-history/08Sep2026-p5-resume-guard-interval-fix.md —
       wave record for the single-writer resume guard on the P5
       supervisor, the recovery of the abandoned forward-test run, and
       the backtest-sanity interval source-of-truth fix; tree returns
       to 395 = ceiling).
  396  P5 evidence-stream isolation wave (2026-09-08): +0
       (scripts/verify_f8h01_external.py check_e now pins
       P5_RUN_LOG_DIR so verification runs stop dropping dry-run stub
       logs into the live reports/ stream; check_repo_hygiene.py gains
       the disk-state guard _p5_dry_run_stubs; .gitignore absorbs
       reports/health/p5-verify-stubs/. No tracked files added.)
  397  F8-H-02 closure-record wave (2026-09-08): +1
       (scripts/verify_f8h02_external.py - outcome-scoped external
       verifier for the Rule-7 per-order modification budget, GREEN/RED
       netted in tests/test_repo_hygiene.py; plus
       docs/audit-history/08Sep2026-f8h02-closure-and-p5-evidence-
       hygiene.md registering F8-H-02 CLOSED with live evidence.
       Ceiling 397 = this tree.)
  397  F8-C-01 wave 2 - options_flow producer (2026-09-08): +0
       (the 5th signal producer lands inside existing modules:
       orchestrator producer + breaker-guarded chain fetch, per_source_
       breakers fleet scope, lockstep gate pins in verify_f8c01_
       external / probe_hc15_strength_gate / fr7_health_check, mock
       walls and real-producer e2e drivers extended, ADR-005 amended
       in place. One new file - docs/audit-history/08Sep2026-f8c01-
       options-flow-producer.md - offset by untracking reports/
       verify_f8h01_external.json: per-run verifier output now writes
       the ignored reports/health/p5-verify-stubs/ path. Ceiling 397
       = this tree.)
  398  09Sep gate-integrity wave (PR #12, merged 2026-09-09): +1
       (tests/test_openalgo_wire_contract.py - wire-contract net for
       the OpenAlgo client surface; supervisor writer-identity tests
       moved to the platform identity contract. Ceiling 398 = this
       tree at the merge.)
  399  Format-surface contract wave (2026-09-09): +1
       (tests/test_format_surface_contract.py - pins root-wide format
       sweep == enforced surface after ruff 0.16's markdown-fence
       scope expansion flagged 40 frozen-evidence docs + 1 live doc:
       frozen via pyproject extend-exclude at the *.md layer only,
       docs/var_engine.md formatted canonical, pre-push pip-audit
       hook mirrors the ADR-0010 waiver. Ceiling 399 = this tree.)
  401  Defense-in-depth gitleaks pre-push net wave (2026-09-10): +2
       (scripts/gitleaks_prepush.py - the F8-C-02 NEXT item landed:
       default-rules gitleaks scan of the push's introduced commits,
       fail-closed on leak/missing binary, wired as the
       gitleaks-prepush local hook in .pre-commit-config.yaml with
       default_install_hook_types covering the pre-push shim;
       docs/audit-history/10Sep2026-gitleaks-prepush-net.md - wave
       record. Ceiling 401 = this tree.)
  402  Analyzer wire-contract route repair (2026-09-10): +1
       (tests/test_openalgo_wire_contract_routes.py - pins every
       client endpoint to the deployment's underscore-free REST route
       (live-verified 10Sep2026: the snake_case spellings 404'd on
       every call, 10,332 position_book 404s during the supervised
       P5 run, breaker flap, CMP funnel starvation) and the
       position-book ltp -> last_price vocabulary alias; ADR-006
       Amendment 3. Ceiling 402 = this tree.)
  403  Analyzer wire-contract wave record (2026-09-10): +1
       (docs/audit-history/10Sep2026-analyzer-wire-contract-route-
       repair.md - the forensic + verification record for the route
       repair above. Ceiling 403 = this tree.)
  405  Analyzer intake decision + breaker isolation wave (2026-09-11): +2
       (docs/audit-history/11Sep2026-analyzer-intake-decision-breaker-
       isolation.md - ADR-006 Amendment 4: the OPEN intake semantic
       resolved to read-only telemetry by operator decision, and the
       5-minute LOATS_P5_Watchdog closing the mid-session supervisor-
       continuity gap; tests/test_analyzer_breaker_isolation.py - the
       RED-first net pinning the dedicated ANALYZER_CIRCUIT_BREAKER that
       isolates routing failures from the shared market-data breaker.
       Ceiling 405 = this tree.)
  407  Analyzer intake-contract setting wave (2026-09-11): +2
       (docs/audit-history/11Sep2026-analyzer-intake-contract-setting.md -
       ADR-006 Amendment 5: analyzer_intake_path as a real per-call-resolved
       setting, so the deferred gateway decision-intake endpoint activates
       via config with zero code change and no restart of the accruing
       14-day P5 span; tests/test_analyzer_intake_contract.py - the
       RED-first net pinning default preservation ("analyze"), per-call
       resolution, endpoint flow, payload immutability, and the single-
       source ceiling. Ceiling 407 = this tree.)
  408  Weekend-session and audited-rejections wave (2026-09-12): +1
       (docs/audit-history/12Sep2026-weekend-session-audited-rejections.md
       - the forensic + verification record: get_current_session was
       weekday-blind (weekends resolved REGULAR and the full CMP funnel
       ran on non-trading days; 529 Saturday signal-batch REJECT rows,
       thousands of weekend cycles in the supervised P5 run), and the
       CMP workflow audited only Step-1 rejections while Steps 2-5
       returned silent dicts (1,024 gating + 3,948 strength rejections
       invisible in the Friday audit trail). Ceiling 408 = this tree.)
  409  P3 carried-set round (2026-09-12): +1 (docs/audit-history/
       12Sep2026-f8-l-carried-set-p3-round.md — the live re-derivation
       record: carried-set verifier 31/31 and F8-M-02..07 verifier 19/19
       green at HEAD, live RSS re-validation 3/3, live P1 round trips
       re-measured (endpoint degraded vs the 04Sep artifact — standing
       risk transferred to the operator), and the F8-L-04 ref-form
       residue (debris branches production-hardening / test-hooks,
       28-29 hook-testing junk commits each, local + origin) purged
       after branch-side exclusivity was proven zero. Ceiling 409 =
       this tree.)
  410  P5 span restart wave (2026-09-12): +1 (docs/audit-history/
       12Sep2026-p5-span-restart-wave.md — the restart-decision
       execution record: zero-decisional run 134427 honestly ended
       (FAIL per the official validator), fresh run 150243 started
       under the hidden-wrapper discipline, watchdog continuity
       upgraded (probe → resume → guarded fresh fallback), and the
       silent-append failure class (cmd >> against the
       supervisor-held log) root-caused and routed to a dedicated
       ops log. Ceiling 410 = this tree.)
  411  Trade-decision persistence coverage wave (2026-09-13): +1
       (docs/audit-history/13Sep2026-trade-decision-persistence-wave.md
       - wave record for the two never-wired async dispatch fixes
       (async_create_trade_decision / async_log_audit) and the
       11-test trade-decision persistence net; db-module margins
       moved 81.9/82.0 -> 85/88 measured. Ceiling 410->411; the
       wave's code delta itself was append-only and held 410.)
  412  Verifier-gate integrity wave (2026-09-13): +1
       (docs/audit-history/13Sep2026-verifier-gate-integrity.md -
       wave record for the two born-red external verifier gates
       repaired to outcome-scoped grading: verify_coverage_full.py
       (undeclared pytest-timeout flag, stale-artifact grading,
       failing-summary substring heuristic, frozen 5-file subset
       scope vs the repo-wide fail_under) and
       verify_todo24_external.py (line-number pin, exact test-name
       list, historical docstring prose on the canonical floor
       gate); +12 regression nets in
       tests/test_todo25_verifier_gates.py sections 8-9. Ceiling
       411->412; the wave's code delta itself was append-only and
       held 411.)
  413  Coverage mutual-exclusion wave (2026-09-13), commit 1 of 2: +1
       (tests/test_coverage_lock_guard.py - 14-test net for the
       conftest coverage-writer lock: --cov runs take an exclusive
       repo-wide lock or are refused rc=4 before any test runs;
       born-RED proven, green in plain and --cov parent modes.
       Ceiling 412->413.)
  414  Coverage mutual-exclusion wave (2026-09-13), commit 2 of 2:
       +1 (docs/audit-history/13Sep2026-coverage-lock-guard-wave.md -
       wave record: writer-class inventory, root cause, guard
       contract, measured verification state. Ceiling 413->414;
       the record itself is the +1 this entry accounts for.)
"""

from __future__ import annotations

TRACKED_FILE_CEILING = 414
