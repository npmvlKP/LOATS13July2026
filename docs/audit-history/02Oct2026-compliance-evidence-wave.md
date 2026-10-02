# 02Oct2026 Wave: Compliance-Evidence Matrix (bulk claims retired)

## Mandate (operator, 02Oct2026)

External review direction: "Replace 'yes, it complies' with an
evidence-based assessment. Tool scans, logging, and a self-imposed rate cap
do not establish compliance with SEBI, NIST, or ISO requirements. For each
applicable requirement, identify the system's regulatory role, the control,
its evidence, the owner, and any gap. SEBI's retail-algo framework and
exchange implementation details require that applicability assessment; the
cited 10 OPS figure alone is not a compliance finding." Cited sources:
SEBI circular SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013 (04Feb2025) and
the NSE retail-algo FAQ (03Nov2025).

## Live evidence gathered before writing (repo + sources)

- Repo prose: `README.md` / `docs/README.md` §Compliance carried the bulk
  assertion ("SEBI Algo Regulations: Full compliance", "NIST 800-53",
  "ISO 27001:2022") with no applicability assessment, no control pointers,
  no gaps. No test or verifier pins those bullets (grep over `tests/` and
  `scripts/verify_*.py`: zero hits), so re-pointing them is a docs-only
  change with zero behavior risk.
- Control evidence verified at HEAD `6c8cf81` before the matrix claimed it:
  - OPS cap: `src/loats/config/settings.py:221` `max_ops = Field(3)`;
    F6-C-01 singleton regression net; HC-14 probe
    (`scripts/probe_hc14_ops_limiter.py`, `verify_hc_registry.py:576`).
  - Kill switch: `src/loats/openalgo.py` + `src/loats/orchestrator.py`
    enforcement; R-17 live drill 01Oct (122 blocked cycles, audited);
    `kill_switch_verified: true` on span JSONs.
  - Audit chain: `src/loats/database.py` (SHA-256 chain, Decimal-aware
    serialization); `tests/test_audit_chain_f9m01.py`,
    `tests/test_audit_dual_write.py`, `tests/test_audit_hash_mutation.py`.
  - Retention default: `settings.py:33` `retention_days: 2555` (7 years).
  - Risk limits: `settings.py:217-231` Decimal fields with quantizing
    validator (:299-301).
  - Admin allow-list: `settings.py:193` `telegram_admin_ids`.
  - Forward-test regime: `scripts/run_p5_forward_test.py` /
    `verify_p5_forward_test.py`; 13 span JSONs 07Sep-02Oct.
- Obligation sources read (web, 02Oct): SEBI circular 0000013 text and the
  NSE implementation circular INVG/67858 (TOPS=10 OPS per exchange/segment;
  static IP + unique client API key; kill switch defined as emergency
  halt / last level of defence; registration trigger above TOPS; family
  sharing per SEBI 03Dec2024 circular; algo-ID tagging).

## What landed

- `docs/COMPLIANCE-MATRIX.md` (NEW): applicability assessment first (LOATS
  is paper-trading/report-only; live-path obligations are operator/broker-
  owned), then per-requirement matrices — SEBI/NSE S1-S8 with
  role/control/evidence/owner/gap columns; NIST 800-53 selected families
  (AU/AC/SC/SI-CM/RA) with explicit no-ATO scoping; ISO 27001 posture
  (no ISMS, no certification); verdict separating evidenced in-repo
  controls from anything not claimed.
- `README.md` + `docs/README.md`: §Compliance bullets replaced with
  posture language that points at the matrix and separates in-repo design
  controls from operator-owned live-path obligations. The Audit Trail
  bullet kept with its in-repo evidence anchors (`retention_days=2555`,
  `src/loats/database.py`).
- `docs/RISK-REGISTER.md`: R-18 row (compliance-by-assertion finding,
  closed by this wave) plus the 02Oct live-state paragraph: span
  `20260929_141804` closed gracefully 18:53 IST (8 restarts,
  kill-switch verified); two watchdog fresh-starts aborted
  (`unhandled_exceptions=1` each) with the root cause live-verified —
  Telegram token `8848435922:***` rejected (masked getMe 401 probe +
  system log 13:28:25Z "Failed start Telegram bot"); revival blocked on
  the operator's BotFather token. R-12's 13Oct span-close arithmetic
  SUPERSEDED: grade the NEXT healthy span's `started_at` (watchdog
  succession rule, R-16).
- `scripts/ratchet_baseline.py`: ceiling 520 -> 522 (this record is the
  second of two new files), history entry appended in the same atomic edit.

## Verification

- Zero behavior change: `git diff` scope is docs-only plus the ratchet
  constant/history (no `src/`, no `tests/`, no `scripts/` logic edits).
- No doc pins break: the only tests reading these files are
  `tests/test_risk_register_current.py` (register shape — appended, not
  rewritten) and `tests/test_cmp_supersession_register.py` (untouched).
- Tree at exactly the new ceiling after staging: `git ls-files | wc -l`
  == `TRACKED_FILE_CEILING` == 522.
- Pre-commit gates on the committed tree: ruff, ruff-format, mypy strict,
  flake8, bandit, pytest, per-module coverage, pip-audit, gitleaks,
  repo-hygiene (the standard net; docs waves still grade through mypy/
  pre-commit).
