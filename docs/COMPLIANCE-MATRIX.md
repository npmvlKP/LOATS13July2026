# LOATS Compliance Posture — Evidence-Based Matrix

Status: AUTHORITATIVE posture document (02Oct2026 compliance-evidence wave).
This matrix supersedes the former bulk assertion ("SEBI: Full compliance;
NIST 800-53; ISO 27001:2022") that previously stood in `README.md` /
`docs/README.md`. External review finding (02Oct2026): tool scans, logging,
and a self-imposed rate cap do not establish compliance with SEBI, NIST, or
ISO requirements; the 10-OPS figure alone is not a compliance finding. For
each applicable requirement this record states the system's regulatory role,
the in-repo control, its evidence, the owner, and the open gap.

Sources of obligation: SEBI circular
`SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013` (04Feb2025, "Safer
participation of retail investors in Algorithmic trading") and the exchange
implementation standards (NSE `INVG/67858`, 05May2025; NSE retail-algo FAQ
03Nov2025). NIST SP 800-53 Rev.5 and ISO/IEC 27001:2022 are voluntary
frameworks; nothing in this repository constitutes certification.

Snapshot: HEAD `6c8cf81` (PR #119 merged 02Oct2026), tree clean, ceiling 520.

03Oct2026 amendment (evidence-cell reconciliation pass): S1 file count
corrected 8 -> 7 (glob-verified at this file's own introducing commit —
birth miscount, no rename history); HC-14 probe re-run clean via repo venv
("3 of 10 acquires accepted"). S6 gap cell superseded by span succession:
revival span `20261002_200805` live (quartet machine-verified), clock to
16 Oct 20:08:05Z — details in the S6 row and the register's 03Oct entry.

## 1. Applicability assessment (read this before the tables)

LOATS is a **paper-trading, analysis, and alerting system**. It runs in
ANALYZE mode: it fetches market data and news, computes signals and risk
figures, routes TradeDecisions to a local Analyzer endpoint, and emits
alerts. It does **not** place live orders. The order path to any exchange
runs — when a user configures it — through the separately deployed OpenAlgo
host and the user's own broker account, not through this repository's code
paths.

Consequences, per the Feb-2025 framework:

- The framework's client-side obligations (algo registration with the
  exchange, static-IP whitelisting, unique client API keys, algo-ID tagging,
  broker OPS policy) attach to the **live client-broker order path**. LOATS
  today sits outside that path; those obligations are **operator-owned**
  (and broker-mediated), not satisfied or discharged by this codebase.
- Controls that bound automated order generation (OPS cap, kill switch,
  audit trail, order/risk validation) are implemented in-repo as **design
  constraints** so that any future live enablement starts compliant; their
  evidence below is real, but it is evidence from the paper path, and this
  matrix says so explicitly.
- The Feb-2025 circular's own trigger for retail algo registration is the
  Threshold Order Per Second (TOPS, initially 10 orders/second per
  exchange/segment): at or below TOPS a tech-savvy retail investor's API
  algos are registration-free; above it, exchange registration through the
  broker is mandatory. LOATS's self-imposed cap is 3 OPS (below TOPS with
  headroom) — that is a design fact, not a regulatory finding.

## 2. SEBI/NSE retail-algo framework — requirement matrix

| # | Requirement (source) | LOATS role today | Control in repo | Evidence | Owner | Gap |
|---|----------------------|------------------|-----------------|----------|-------|-----|
| S1 | Order rate <= TOPS 10 OPS per exchange/segment (SEBI Feb-2025; NSE INVG/67858 §B) | None live — no orders placed. Binding design bound for any future live path. | Shared `RateLimiter`, `max_ops: int = Field(3, ...)` (`src/loats/config/settings.py:221`); singleton accessor F6-C-01 regression net; HC-14 probe (`scripts/probe_hc14_ops_limiter.py`, `scripts/verify_hc_registry.py:576`) | `tests/test_rate_limiter*.py` (7 files incl. factory-regression + settings-integration); HC-14 in `verify_hc_registry.py` ("3 of 10 acquires accepted", probe re-run 03Oct2026 via repo venv) | Engineering (control); operator (any live-path enforcement by broker) | Cap is enforced in code, but all evidence is from the paper path; no broker-side enforcement exists or is claimable from this repo |
| S2 | Algo registration with the exchange (required above TOPS; family sharing rules) | N/A — no live order path, and no >10-OPS algorithm exists | Not applicable in-repo | n/a | Operator + broker (registration is filed through the broker) | Opens the day live trading is enabled; recorded here so the trigger is explicit |
| S3 | Static IP + unique client-specific API key; no open APIs (SEBI Feb-2025 §I.d) | Out of repo scope — broker connectivity lives in the operator's host/broker config | None (documented posture only) | n/a | Operator + broker | Operator must provision static IP + per-client API key before any live enablement; nothing in LOATS can satisfy this |
| S4 | Kill switch — emergency halt, last level of defence (SEBI Feb-2025 fn.4; exchange supervision) | Implemented and exercised: kill switch halts the orchestrator cycle loop and cancels broker orders via the host | `src/loats/openalgo.py` (activate/deactivate), `src/loats/orchestrator.py` (blocking enforcement), disclosure ADR-0018, escalation/acceptance ADR-0020 | R-17 live drill 01Oct2026: activation 08:03:04.842Z, 122 consecutive orchestrator-blocked cycles, deactivation 08:05:12.057Z, zero TypeErrors post-#114 (`3b93fe5`); span JSONs carry `kill_switch_verified: true`; refusal semantics proven (13:14 IST fail-closed rollback) | Engineering (control); operator (drill cadence) | In-span exercise is a per-span deadline (14-day clock); span succession resets it — see R-16/R-18 in `docs/RISK-REGISTER.md` |
| S5 | Audit trail / traceability of algorithmic activity | Implemented: append-only, SHA-256-chained audit log (JSONL + SQLite dual write) with tamper-evidence tests | `src/loats/database.py` (hash chain, Decimal-aware serialization at :778), every routed decision leaves a chained `ROUTE` row | `tests/test_audit_chain_f9m01.py`, `tests/test_audit_dual_write.py`, `tests/test_audit_hash_mutation.py`, repair fidelity `tests/test_repair_backup_fidelity.py` (R-15); 95/95 ROUTE rows 01Oct `recorded: true` | Engineering | 7-year retention is a default (`retention_days: 2555`, `settings.py:33`), not a certified archival regime; backup/DR rehearsal still open (R-15 note) |
| S6 | Testing SOP / simulation before deployment (exchange supervision duty; broker-side testing gates) | Supervised forward-test regime: P5 span with supervisor, watchdog, counter quartet, fail-closed grading | `scripts/run_p5_forward_test.py`, `scripts/verify_p5_forward_test.py` (zero unhandled exceptions, routing enabled, measured decisional activity — hard FAIL per ADR-006 Am.2), ADR-006 amendments 1-8 | `reports/p5_forward_test_*.json` family (14 spans 07Sep-02Oct; newest `20261002_200805` = live revival span), R-12 counter-carry fix (`fix/p5-resume-counter-carry`) | Engineering (harness); operator (span ops) | No live span currently exists (02Oct token incident, R-18) — SUPERSEDED by succession 03Oct2026: the healthy revival span `p5_forward_test_20261002_200805` is LIVE since 2026-10-02T20:08:05Z (green quartet machine-verified 03Oct: `ended_at` null, `unhandled_exceptions: 0`, `kill_switch_verified: true`, fresh sample); the 14-day accumulation clock runs to 2026-10-16T20:08:05Z per R-16 succession, and the in-span kill-switch exercise remains outstanding on this span |
| S7 | Algo-ID tagging of order messages | N/A — no live orders; tagging is broker-side at live time | Not applicable in-repo | n/a | Broker + operator | Recorded for the live-enablement checklist |
| S8 | Risk controls on automated order generation (halting malfunctioning algos) | Implemented: circuit-limit %, max order value, max total exposure, Decimal quantization | `settings.py:217-231` (`max_order_value` 200000.00, `circuit_limit_pct` 0.05, `max_total_exposure` 1000000.00), `validate_decimals` quantize to 0.01 (`settings.py:299-301`) | Settings validators + `tests/` risk-path coverage; per-module coverage floors in `scripts/check_per_module_coverage.py` | Engineering | Paper-path evidence only; live-path risk-engine acceptance would require its own supervised window |

## 3. NIST SP 800-53 — selected families, honest scoping

LOATS is a single-host research system. **No ATO exists, no independent
800-53 assessment has been performed, and the system does not claim 800-53
compliance.** Selected families where real, evidence-linked controls exist:

| Family | Control in repo | Evidence | Gap |
|--------|-----------------|----------|-----|
| AU (Audit & Accountability) | Chained append-only audit log; structured JSON logging; 7-year retention default | S5 above; `src/loats/loats_logging.py` | No centralized SIEM, no log-review workflow |
| AC (Access Control) | Telegram admin allow-list (`telegram_admin_ids: list[str]`, `settings.py:193`); secrets via env + `SecretStr` (`settings.py`), `.env` git-ignored (repo-hygiene hook blocks tracked env files) | Pre-commit `repo-hygiene` hook; `.pre-commit-config.yaml:142` | No MFA/SSO surface; single-operator model assumed |
| SC (System & Communications Protection) | Host API bound to loopback (observed `127.0.0.1:5000` LISTENING, 02Oct); no external ingress in-repo | Live netstat observation at record time | TLS/host-hardening is host-side (OpenAlgo), not this repo |
| SI / CM (integrity & config) | Pinned settings with validators; duplicate-listener preflight refusal (`src/loats/preflight.py::check_duplicate_listener`, R-08); dependency manifest sync hook | `tests/test_preflight_r08.py`; `deps-sync` pre-commit hook | No continuous config-drift monitoring |
| RA / vulnerability mgmt | pip-audit + bandit + gitleaks gates on every push (waiver ADR-0010 documented) | `.pre-commit-config.yaml:108,128`; README quality-gates block | Shared-venv ambient audits (R-05) — fresh-venv replication recipe required for authoritative audits |

## 4. ISO/IEC 27001:2022 — posture

**No ISMS exists. No certification, no Statement of Applicability, no risk
register certified to the standard.** Engineering practices that map to
Annex A themes and are evidenced in-repo: secure development gates (bandit,
gitleaks, pip-audit, mypy strict, coverage floors), asset/config discipline
(pinned settings, tracked-file ceiling with history), cryptographic
integrity of audit records (SHA-256 chain), incident-response primitives
(kill switch, breaker isolation ADR-006). These are engineering controls,
not management-system controls; the gap is organizational and out of repo
scope.

## 5. Verdict

- **Evidenced in-repo (paper path):** OPS cap <= 3 with regression nets;
  kill switch with a live drill record; SHA-256-chained append-only audit
  trail; risk limits with Decimal quantization; supervised forward-test
  regime with fail-closed grading; secret-hygiene and dependency gates.
- **NOT evidenced, NOT claimed:** any regulator- or exchange-facing
  compliance determination; NIST 800-53 or ISO 27001 certification; the
  adequacy of any future live order path (S2/S3/S7 are operator-owned and
  open until live trading is ever enabled).
- Bulk "full compliance" claims are retired. Any future compliance
  statement must be added to this matrix with a row, evidence, and owner —
  never as a header bullet.
