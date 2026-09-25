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
  415  Bandit nosec-currency wave (2026-09-13), commit 1 of 2: +1
       (tests/test_bandit_nosec_currency.py - 3-test net: zero
       "nosec encountered" notes on the src/ scan, zero findings,
       retry.py B311 annotation pinned; born-RED proven with exactly
       the four database.py notes. Ceiling 414->415.)
  417  Bandit nosec-currency wave (2026-09-13), commit 2 of 2:
       +2 (docs/adr/0015-bandit-nosec-currency.md +
       docs/audit-history/13Sep2026-bandit-nosec-currency-wave.md -
       decision + wave record for the four suppress-token refactors
       and the note-attribution root cause. Ceiling 415->417; the
       two records are the +2 this entry accounts for.)
  418  FR7 TODO disposition re-verification (2026-09-14): +1
       docs/audit-history/14Sep2026-fr7-todo-disposition-reverification.md
       (live re-grade of the 01Sep disposition table at HEAD e648f91;
       the +1 is this record. Ceiling 417->418.)
  419  Appendix C disclosures resolution (2026-09-14): +1
       (docs/audit-history/14Sep2026-appendix-c-disclosures-resolution.md
       - live re-verification of the six 01Sep Appendix C "not enough
       evidence" disclosures: 4 resolved with execution evidence, 2
       carried by design. Ceiling 418->419; the record is the +1 this
       entry accounts for.)
  421  F9-C-01 iv_rank correctness wave (2026-09-15): +2
       (tests/test_iv_rank_f9c01.py - 21-test regression net for the
       iv_rank saturation fix, RED-first proven; and
       docs/audit-history/15Sep2026-F9C01-TODO1-resolution.md - the
       resolution record. Ceiling 419->421; both files are the +2 this
       entry accounts for.)
  422  FR9 forensic-review record wave (2026-09-15): +1
       (docs/audit-history/15Sep2026-FR9-forensic-review-report.md -
       the 15Sep2026 FR9 forensic engineering review report, relocated
       from the staged root copy "15Sep2026-FR-ToDo List.md" per its
       own Appendix disposition note; the root-staged file was the
       422nd tracked file that breached this ceiling and failed the
       repo-hygiene gate. Ceiling 421->422; the record is the +1 this
       entry accounts for.)

  423. 15Sep2026 (F9-C-02 / TODO-2 wave, commit 4 of 5): regression
       suite tests/test_p5_f9c02_routing_guard.py (33 tests pinning the
       routing provenance guard + grader-visible divergence counter,
       the exclusive-bind metrics port + boot refusal, the supervisor
       identity/DB-reconciliation evidence stamps, the grader's
       divergence hard-FAIL + fail-closed evidence shapes + legacy
       contamination windows, and the reconciliation helper's DB
       contract). Ceiling 422->423.

  424. 15Sep2026 (F9-C-02 / TODO-2 wave, commit 5 of 5): resolution
       record docs/audit-history/15Sep2026-F9C02-TODO2-resolution.md
       (root cause, remediations, adversarial-grading hardening wave,
       live verification evidence). Ceiling 423->424; the record is
       the +1 this entry accounts for.)

  425. 16Sep2026 (P5 drought re-check, separate wave): re-check record
      docs/audit-history/16Sep2026-p5-wednesday-recheck.md (GO/NO-GO
      verdict + provenance-locked evidence addendum). Ceiling 424->425;
      the record is the +1 this entry accounts for.

  426. 16Sep2026 (P5 restart execution, FR9 condition closed):
      docs/audit-history/16Sep2026-p5-restart-execution.md - honest
      CTRL_C end of void span 150243 (official FAIL: 15 divergent
      ROUTE rows + 3.96d span), autonomous watchdog fresh fork of
      140341 with routing enabled, route-watch repointed, grading
      cron re-armed 26->30Sep 21:00 IST. Ceiling 425->426; the
      record is the +1 this entry accounts for.

  427. 17Sep2026 (F9-H-02 prerequisite wave): decision record
      docs/adr/0016-defer-cycle-latency-budget-wire-benchmark-gate.md
      (cycle-latency budget decision deferred past the 30Sep P5
      checkpoint; CI benchmark-perf gate wired advisory; born-red
      stage-budget defect root-caused and fixed). Ceiling 426->427;
      the ADR is the +1 this entry accounts for.

  429. 17Sep2026 (F9-H-04 / TODO-5 wave): +2 -- the acceptance net
      tests/test_f9h04_as_of_date_wiring.py (live-cycle snapshot-date
      derivation pins) and the resolution record docs/audit-history/
      17Sep2026-F9H04-TODO5-resolution.md (root cause, remediation,
      RED/GREEN evidence). Ceiling 427->429.
  431. 17Sep2026 (F9-C-02 outage-reflection wave): +2 -- the outage
      registry net tests/test_p5_f9c02_outage_window.py (13 pins:
      DOCUMENTED_OUTAGE_WINDOWS shape, annotation-only semantics,
      contamination VOID unchanged, CLI NOTE surfacing) and the dated
      outage record docs/audit-history/
      17Sep2026-p5-openalgo-auth-outage.md (relocated from the
      untracked reports/p5_auth_outage_20260917.md, which had zero
      ignore coverage -- the 430-vs-429 re-arm vector; addendum
      documents the open-ended window + closing-entry template).
      Ceiling 429->431.
  433. 17Sep2026 (F9-H-03 / TODO-4 remediation wave): +2 -- the
      remediation net tests/test_sentiment_f9h03_producer.py (15 pins:
      article-content cache, LKG serving + detached cache-only refresh,
      degraded provenance tagging, per-source liveness alert) and the
      resolution record docs/audit-history/
      17Sep2026-F9H03-sentiment-producer-resolution.md (root cause:
      per-article downloads overrun the producer window so cancellation
      lands before every persist; remediation + span-safety statement).
      Ceiling 431->433.
  435. 17Sep2026 (F9-M-01 / TODO-6 remediation wave): +2 -- the chain
      net tests/test_audit_chain_f9m01.py (15 pins: link-walking
      verifier vs delete/reorder/mutate, grandfathered legacy prefix,
      head-seed extension, schema-index parity fresh-vs-migrated,
      positional row reader, migration idempotence, 1k chain) and the
      resolution record docs/audit-history/
      17Sep2026-F9M01-audit-chain-resolution.md (self-hashing cannot see
      deletion/reorder; genuine sha256(entry||prev) chain on both
      writers; CRITICAL alerts). Ceiling 433->435.
  437. 18Sep2026 (F9-M-05 / TODO-15 remediation wave): +2 -- the CMP S4
      conformance net tests/test_strike_selection_f9m05.py (28 pins:
      closed delta band 0.49/0.50/0.60/0.61 boundaries, put-magnitude
      symmetry, OI confirmation fail-closed, hand-computed sigma and
      2-sigma band, mixed/unparseable-interval fail-closed, insufficient
      -history fail-closed, max_strikes cap, empty chain, ATM-pair dedup
      root-cause pins) and the resolution record docs/audit-history/
      18Sep2026-F9M05-strike-band-resolution.md (open-band heuristic
      rejected 0.60 exactly; zero sell-side logic; ATM pair produced
      [K, K]). Ceiling 435->437.
  439. 18Sep2026 (F9-M-03 / TODO-8 resolution wave): +2 -- the
      audited-attempt semantics net tests/test_f9m03_audited_attempt.py
      (17 pins: the machine-readable semantic source, per-path attempt
      counting -- success, designed-404 error, disabled -- the
      attempts>=outcomes invariant, the grader attempt-gate branches
      (PASS / legacy-unchanged / ended-FAIL / ongoing-INCOMPLETE),
      divergence non-whitewash, supervisor baseline+delta fold; plus 2
      pins carried in tests/test_analyzer_intake_contract.py for the
      Am.7 semantic source and the worktree-shape coverage-lock pins in
      tests/test_coverage_lock_guard.py) and the resolution record
      docs/audit-history/18Sep2026-f9m03-audited-attempt-semantics.md
      (ADR-006 Amendment 7 option (a): routed ATTEMPTS are the P5
      decisional evidence; same-wave root-cause fix: coverage-lock
      guard worktree-safe in tests/conftest.py). Ceiling 437->439.

    2026-09-18 (F9-C-01-R1 taint-exporter wave): +2 tracked files --
      scripts/export_infinity_taint.py (read-only forensic exporter:
      inventories pre-fix -Infinity audit rows into a sidecar RFC 8259
      manifest; SQLite opened mode=ro, JSONL read-only, inventory-not-
      error exit semantics) and tests/test_infinity_taint_exporter.py
      (12 contract tests, RED-first proven). Live-store scan 18Sep:
      17,289 JSONL lines + both SQLite surfaces, 0 tainted rows,
      store SHA-256 identical before/after. Ceiling 439->441.

    2026-09-18 (F9-C-02 closure wave): +2 tracked files --
      tests/test_p5_f9c02_kill_switch_and_archive.py (16 pins, RED-first
      proven: the CMP P5 gate's kill-switch verification event --
      supervisor probe `_probe_kill_switch` + `_record_kill_switch_
      verification` stamps `kill_switch_verified` /
      `kill_switch_active_at_start` and the verification/alarm event at
      supervision start, fresh + resumed + dry-run; grader fail-closed
      criterion `_grade_kill_switch_evidence` -- an ENDED run without
      disengagement proof FAILs, an ongoing run carries the reason,
      engaged switch FAILs even when verified; the deferred finding
      item 1 discharged via the dated INVALID-EVIDENCE archive record
      citing the official grader rc=1 verdict on the real poisoned
      artifact, re-proven in-suite) and docs/audit-history/
      18Sep2026-F9C02-invalid-evidence-archive.md (marks run
      20260912_150243 INVALID-EVIDENCE, verbatim grader output, evidence
      chain, citation rule; also documents this closure wave).
      Production edits (scripts/run_p5_forward_test.py,
      scripts/verify_p5_forward_test.py) land within the existing
      ceiling; 5 legacy PASS-shaped fixtures healed in tests/
      test_p5_forward_test.py, test_p5_f9c02_routing_guard.py,
      test_p5_f9c02_outage_window.py, test_f9m03_audited_attempt.py,
      test_f8h01_fixes.py and scripts/verify_f8h01_external.py.
      Ceiling 441->443.
    * 443->444 (2026-09-19, PR #60 follow-up): the two evidence pins in
      tests/test_p5_f9c02_kill_switch_and_archive.py graded the
      GITIGNORED live artifact reports/p5_forward_test_20260912_150243.json
      (CI-leakage hermeticity failure: fresh checkouts lack the
      machine-local file; live-verified 2026-09-19, pytest-coverage red on
      PR #60). Fix: tracked verbatim fixture
      tests/fixtures/p5_run_log_20260912_150243_snapshot.json (programmatic
      projection of the artifact of record, graded signature identical),
      pins re-pointed to it, both environments green 16/16. +1 tracked
      fixture file within this headroom.
      Ceiling 443->444.
    * 444->446 (2026-09-19, P5-OPS-01 span-invariants wave): +2 tracked
      files -- tests/test_p5_f9c02_span_invariants.py (19 pins,
      born-RED proven: grader kill-switch proof re-derived SPAN-attached
      from writer generations, supervisor market-data availability fold,
      PowerShell-safe verify_exit_code_battery) and docs/audit-history/
      19Sep2026-p5-span-invariants.md (the wave record: generation
      model -- every writer_claimed opens a generation, pre-claim events
      form the fresh-start generation, kill_switch_alarm records
      verified:false; ENDED runs FAIL-closed unless EVERY generation
      proves the halt; availability fold unverified-on-probe-failure,
      annotation-only in the grader; the 19Sep [bool]*[int] ledger
      abort). Ceiling 444->446.
    * 446->447 (2026-09-20, F8-V-01 verification-instrument wave): +1
      tracked file -- scripts/verify_f8v01_basetemp.ps1 (the PS 5.1
      companion recipe: unique-basetemp-per-session insulation with the
      forward-slash sanitization, live-validated end-to-end 118 passed
      rc=0; born from the 20Sep shared-explicit-basetemp poisoning wave
      -- sibling session rm_rf deleted the hygiene probe's tmp_path
      config mid-run, flake8 7.x banner-on-stdout silent death made the
      reports/ai-generated grant class vanish, see F8-V-01 in
      tests/test_repo_hygiene.py). The hygiene-module fix itself is a
      test edit (+36/-7) within the existing tree.
      Ceiling 446->447.
    * 447->450 (2026-09-20, F9-H-03 BG-1 close-out wave): +3 tracked
      files -- tests/test_cache_tiered_ttl_f9h03.py and
      tests/test_sentiment_ttl_horizons_f9h03.py (the BG-1 pins: per-entry
      TTL honored via per-TTL tier stores, expiry strict, delete/clear/
      stats span all tiers, and the sentiment horizon chain
      freshness(300) < degraded-threshold(600) < retention(900) that
      makes degraded=True reachable) and docs/audit-history/
      20Sep2026-F9H03-verification-and-BG1-closeout.md (the wave record:
      CacheManager.set ignored per-call ttl= under the single-TTLCache;
      freshness/threshold/retention chain). Source changes stayed within
      the existing tree (cache.py, sentiment.py, conftest.py, test_cache.py).
      Ceiling 447->450.
    * 450->453 (2026-09-21, F9-H-05 CMP-P3 wave): +3 tracked files --
      tests/test_sentiment_p3_ensemble_f9h05.py (the RED-first pins:
      hard [-1,+1] model bounds, 4 h half-life decay arithmetic vs
      hand-computed values, decay monotonicity, seeded-fuzz
      aggregation bounds, news-only ensemble scaffold, cold-path
      delegation onto the single aggregation core),
      docs/adr/0017-p3-sentiment-ensemble-decay-bounds.md (the
      decision: bounds as a model invariant; decay applied
      pre-average; the social leg ADR-deferred -- never fabricated),
      and docs/audit-history/21Sep2026-F9H05-p3-ensemble-decay-bounds.md
      (the wave record). Source changes stayed within the existing
      tree (sentiment.py ensemble core + cold-path dedup onto
      _compute_and_count, models.py Field bounds,
      test_sentiment.py naive-datetime correction).
      Ceiling 450->453.
    * 453->456 (2026-09-21, risk-register wave): +3 tracked files --
      docs/RISK-REGISTER.md (the tracked risk register replacing the
      chat/paste transcript: paste lag re-proven 21Sep -- F9-H-03 was
      already closed at HEAD when the register carried it open),
      tests/test_risk_register_current.py (content pins: register
      present, P1 items carry the 30Sep due date, R-01 cites the live
      cycle count, R-02 names generations 1..3 and the two closure
      options, closed references cite 07ab8ae and 633daae), and
      tests/test_p5_verifier_frozen_infra.py (a frozen-infra test file
      per the inf-runner classification: pins verify_p5_forward_test's
      grading behavior by direct-function invocation -- P5-OPS-01
      generation derivation, span-attached kill-switch grading, and
      documented-outage annotation never grading -- so the 30Sep
      checkpoint cannot move the gate mid-stream without a visible,
      RED-proven test change; no CI job named inf-runner exists at
      633daae, none introduced).
      Ceiling 453->456.
    * 456->458 (2026-09-21, R-02 ADR-0018 wave): +2 tracked files --
      docs/adr/0018-p5-preguard-killswitch-disclosure.md (the R-02
      decision: generations that OPENED before P5_GUARD_CUTOFF
      (2026-09-19T00:00:00+00:00, midnight before the first guarded
      opening) disclose as NON-GRADING annotations; post-guard and
      unknown-vintage holes stay FAIL-closed -- vintage is re-derived
      from the event stream, never declared), and
      docs/audit-history/21Sep2026-p5-preguard-killswitch-disclosure.md
      (the wave record: live-artifact before/after grading, poisoned
      snapshot FAIL preserved, RED/GREEN net evidence). Source changes
      stayed within the existing tree (verify_p5_forward_test.py
      opened_at/P5_GUARD_CUTOFF/_pre_guard_kill_switch_generations +
      grader split; run_p5_forward_test.py delegation + --status
      NOTE surface; frozen-infra/span-invariants/register pins
      re-based). Ceiling 456->458.
    * 458->459 (2026-09-23, R-07 docs wave): +1 tracked file --
      docs/audit-history/23Sep2026-orphaned-mutant-sweep-recovery.md
      (the orphaned fixer-hook mutant sweep incident record and
      recovery protocol; register R-07 section + header update and the
      F9-H-05 record §4 erratum landed in the same wave, no other new
      files). Ceiling 458->459.
    * 459->461 (2026-09-23, FR9 Wave 4 c1 -- F9-L-03 provenance
      guard): +2 tracked files -- src/loats/signal_source_guard.py
      (insert-time enum-source guard on both signal write paths) and
      tests/test_signal_source_guard.py (guard contract + store-policy
      nets). Ceiling 459->461.
    * 461->463 (2026-09-23, FR9 Wave 4 c2 -- F9-L-03 audited purge):
      +2 tracked files -- scripts/purge_legacy_signal_rows.py
      (dry-run-default audited purge: single-writer probes, safety
      copies, audit-first chained DELETE entries, second-instance
      verification) and tests/test_purge_script_f9l03.py (12 pins).
      Ceiling 461->463.
    * 463->465 (2026-09-23, FR9 Wave 4 c3 -- F9-L-04/F9-L-05 decisions):
      +2 tracked files -- docs/adr/0019-cmp-supersession-register.md
      (the register's authority record) and
      docs/adr/0020-killswitch-escalation-analyze-acceptance.md
      (binary switch accepted for the ANALYZE horizon; 3-state machine
      deferred to a PRE-LIVE gate with a binding spec). Ceiling
      463->465.
    * 465->467 (2026-09-23, FR9 Wave 4 c4 -- the register itself):
      +2 tracked files -- docs/CMP-SUPERSESSION-REGISTER.md (15 rows
      S-01..S-15: expectation / delivered reality / authority / state;
      includes S-14/S-15 holding the L-01/L-02 30Sep slots) and
      tests/test_cmp_supersession_register.py (7 content pins).
      Ceiling 465->467.
    * 467->469 (2026-09-23, FR9 Wave 4 c5 -- disposition record and
      dry-run evidence): +2 tracked files --
      docs/audit-history/23Sep2026-fr9-wave4-low-tier.md (the wave
      record: L-03 executed/staged, L-04/L-05 closed, L-01/L-02
      scheduled to the 30Sep wave, L-06 reconciled) and
      reports/ai-generated/f9l03-purge-record.json (the audited
      dry-run evidence: 42 eligible rows classified, 5 valid-tag
      rows retained, STRESS-ORD present). Ceiling 467->469.
    * 469->470 (2026-09-24, F9-M-02 branch-protection closure wave,
      landed via the FR9-Wave-4 ancestry merge, PR #72 merge 7516e83):
      +1 tracked file --
      docs/audit-history/24Sep2026-F9M02-branch-protection-closure.md
      (the closure record: classic branch protection re-enabled via the
      REST API after the silent 404 regression, 10 required contexts per
      the documented contract, live direct-push 403 and fast-forward
      rejection probes; register header update and the CONTRIBUTING.md
      drift correction landed in the same wave, no other new files).
      Ceiling 469->470.
    * Parallel lineage (branch
      fix/breaker-mirror-reset-and-outcome-instrumentation, grown from
      the same 459 baseline; reconciled into main by the PR #72-#75
      merge flow, 2026-09-24):
    * 459->461 (2026-09-23, 30Sep evidence wave, commit 1/5): +2
      tracked files -- src/loats/signal_outcomes.py (pure
      outcome-grading core) and tests/test_breaker_mirror_lifecycle.py
      (the breaker-mirror RED/GREEN lifecycle net); the orchestrator
      mirror reset rides this commit within the existing tree.
      Ceiling 459->461.
    * 461->462 (same wave, commit 2/5): +1 tracked file --
      tests/test_signal_outcomes_db.py (the outcome storage
      persistence net); database.py outcome storage + async additions
      ride this commit within the existing tree. Ceiling 461->462.
    * 462->464 (same wave, commit 4/5): +2 tracked files --
      tests/test_signal_outcomes_core.py (grading fuzz + arithmetic
      nets) and tests/test_signal_outcomes_wiring.py (orchestrator
      wiring net); the settings knob rides the same wave in-tree.
      Ceiling 462->464.
    * 464->465 (same wave, commit 5/5): +1 tracked file --
      docs/audit-history/23Sep2026-breaker-mirror-and-outcome-
      instrumentation.md (the wave record; settings knob +
      .env.example landed in-tree with commit 3/5). Ceiling 464->465.
    * 465->468 (2026-09-24, F9-M-01-R1 frozen-chain-head wave): +3
      tracked files -- src/loats/database_async_additions.py chain
      writer repair rides the existing tree, so the delta is the
      fail-closed re-anchor tool scripts/repair_f9m01_chain_head.py
      (live-cited in RUNBOOK.md Audit Log Integrity), its concurrency
      regression net tests/test_audit_chain_f9m01_async_writer.py, and
      the wave record docs/audit-history/
      24Sep2026-f9m01-r1-frozen-chain-head-resolution.md. Ceiling
      465->468.
    * 470->479 (2026-09-24, PR #72 ancestry-merge reconciliation):
      merged union of the two parallel lineages -- main at 470 after
      PR #72 plus the 9 evidence-wave files above (zero filename
      overlap between the branches) = 479 tracked files. Ceiling
      470->479.
"""

from __future__ import annotations

TRACKED_FILE_CEILING = 479
