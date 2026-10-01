# 01Oct2026 — MCX/CDS segment-enablement wave: per-segment sessions, NoDecode env parsing fix, suite ambient-env pin

- **Wave:** operator mandate (01Oct2026, highest priority): the trading
  setup must mandatorily consider MCX and forex (exchange-traded CDS)
  instruments alongside NSE/NFO.
- **Base:** `main` @ `f6ea101` (post-#115), tree clean, ceiling 513
  pre-wave. Branch `feat/mcx-cds-segment-enablement`.
- **Commits:** `ab646d7` (feat(segments): 7 files, +420/−3, ceiling
  re-pin 513→515 in-commit per the at-ceiling split rule) and
  `b48c043` (fix(verifier): 01Oct outage-close re-dating, 1 file).
- **Mode:** ANALYZE end-to-end; no order-path code touched; the P5
  gen14 span was preserved across the required C-2 restart
  (`restarts` 3→4, `started_at` unchanged, kill-switch verified true).

## 1. Live evidence base (probes, not assumptions)

- Master contracts for MCX and CDS were ALREADY downloaded and live on
  the running OpenAlgo host: `/api/v1/search` returned populated
  contract rows for both segments; quotes probes returned real data
  (GOLD fut LTP 150022 OI 16195; CRUDEOIL fut; USDINR fut 96.845).
  Earlier bare-symbol failures ("Symbol 'GOLD' not found") were
  symbol-format error, not missing contracts — MCX/CDS symbols are
  full contracts (GOLD04DEC26FUT, USDINR01OCT26FUT).
- 2026 holiday calendars were generated from OpenAlgo's live
  `/api/v1/market/holidays` (Zerodha-sourced): NSE closed 16 days,
  MCX closed only 4 days (Republic Day, Good Friday, Gandhi Jayanti,
  Christmas) — MCX trades through Dussehra (2026-10-20) when NSE is
  shut; CDS closed 16 days. No hand-curated dates.
- The host's decision intake (`/api/v1/analyze`, fork head
  `a51822b4`, PR #2047 open upstream) was probed live: empty body →
  400 (route registered and served by the RUNNING process).

## 2. Implementation

- `src/loats/segments.py`: per-segment session registry — NSE
  09:15–15:30 (legacy contract preserved bit-for-bit), MCX 09:00–23:30,
  CDS 09:00–17:00; segment holiday sets; `segment_for_exchange`
  (NFO/BFO/BSE roll into the NSE session segment); `is_segment_open`;
  `enabled_segments` (canonical order, NSE-only default);
  `any_enabled_segment_open` for the follow-up per-segment engines.
- `settings.py`: `ENABLED_SEGMENTS` (documented comma form, validated),
  default `NSE` — behavior-preserving until the operator adds segments.
- `scheduler.py`: market-status job logs per-segment session state.
- The orchestrator cycle gate was deliberately NOT changed mid-span:
  the cycle runs unconditionally by design (kill-switch-gated) and the
  feeds/strategies own data-session semantics; per-segment producers
  consume `is_segment_open` in the next wave.

## 3. Defects found and fixed during the wave (all root-caused)

- **NoDecode comma-form bug (real, pre-existing):** pydantic-settings
  JSON-decodes complex fields before validators run, so the documented
  `ENABLED_SEGMENTS=NSE,MCX` form died with SettingsError before any
  validator could parse it. Surfaced as a 185-test error cascade when
  the suite's conftest pinned the field as a plain string. Fixed with
  `Annotated[list[str], NoDecode]` plus a validator accepting comma and
  JSON forms; five parsing regression pins added (17-case net total).
- **Suite ambient-env coupling:** 13 factory/cycle tests inherited the
  operator `.env` (`ANALYZER_ROUTING_ENABLED=true` — the correct
  production posture activated this same evening, C-1/C-2 with full
  read-backs) and failed against the factory-default expectation.
  Causation proven (52/52 green with the variable explicitly false);
  durable fix: conftest pins the suite baseline via `setdefault`
  (injected environments still win) per the knob-adoption contract.
- **Format surface:** the enforced formatter is `ruff format` (no
  black in the venv); two new/edited files reformatted; full surface
  re-verified (231 files clean).
- **ASCII gate:** an em-dash in a `src/` comment failed
  `TestSrcAsciiGate`; replaced with ASCII `--`.
- **Verifier re-dating (separate commit):** the uncommitted 01Oct edit
  re-dated the pre-band outage close 02:50:21Z → 07:50:21Z. Verified
  against the LOATS rotation family (global breaker CLOSED 07:50:21Z,
  four source breakers by 07:50:52Z; zero close events in 02:5xZ) and
  the merged audit-history Continuation 6 (same 07:50:21Z, "29 s after
  re-auth"), which also resolves the comment's internal 07:19:52Z vs
  13:19:52 IST contradiction (re-auth = 07:49:52Z).

## 4. Verification

- Full suite on the exact shipping tree: **2363 passed / 1
  by-design skip / 0 failed**, coverage **89.62%** (gate 80%).
- mypy strict `src`: clean, 43 files; ruff + ruff-format + bandit +
  isort clean on all touched files; pre-commit 17/17 green on both
  commits (the first split attempt was correctly refused by the
  type-coupled-tree check — wave-before-verifier ordering is the only
  hook-consistent order; the intermediate mis-split (verifier swept
  into the wave commit) was caught pre-push by the file-set read-back
  and repaired via soft reset: unpushed history is free to rewrite).

### 4a. Venv dependency remediation (push-gate fail-closed catch)

The first pre-push run REFUSED the branch: its dependency-audit leg
fail-closed on 4 PYSEC advisories in `virtualenv 21.7.5` — advisories
an earlier manual check had reported clean, because the check piped
pip-audit through `tail` and captured the LAST COMMAND's exit code,
reading only the head of the vulnerability table (the exact
documented `$?-after-a-pipe` trap). Root-cause fix, not a hook
allowlist: `virtualenv` upgraded 21.7.5→21.14.2, `urllib3`
2.7.0→2.8.0 (three CVEs, fix 2.8.0), and `nltk 3.10.3` (PYSEC, no fix
version) REMOVED as an undeclared leftover — the locked reference
venv (R-05) never carried it and the optional-[nlp] design treats its
absence as supported (F8-L-06 knob). Post-remediation pip-audit:
rc=0, zero findings; posture now byte-identical to the R-05 baseline
(urllib3 2.8.0 / virtualenv 21.14.2). Lesson: a clean pip-audit claim
is only evidence when the rc was captured without a truncating pipe.
Second drift catch by the same tripwire net: the pre-push aggregate
suite then failed
`TestAdvisoryWaiverSurfaceLockstep::test_waiver_still_matches_installed_toolchain`
— the ADR-0010 waiver-currency guard firing BY DESIGN in the
"safety present, nltk absent" quadrant (removal trigger B). The
arbiter is the lockfile: uv.lock contains NEITHER safety NOR nltk, so
the installed `safety 3.8.1` (and its nltk requirement) was legacy
drift, not an upstream trigger. safety removed (restoring the
audit-only quadrant, where the guard SKIPs as designed); CI/security
surfaces keep the `--ignore-vuln PYSEC-2026-3740` flag in lockstep
per ADR-0010. Final posture: pip check clean, pip-audit rc=0, format
surface 35 passed + 1 by-design skip.

## 5. Operational state at wave close

- C-1/C-2 verified earlier the same evening: routing enabled
  (`ANALYZER_ROUTING_ENABLED=true`, `ANALYZER_INTAKE_PATH=analyze`),
  LOATS restarted through the production entry point with the
  watchdog-choreography (disable → swap → verify → re-enable), gen14
  span preserved, Analyzer toggle confirmed ON host-side.
- Automated Zerodha broker re-login cron (08:35 IST, market days,
  vault-backed TOTP) upgraded to a multi-segment calendar gate: skips
  only when NSE, NFO, MCX and CDS are ALL closed; an NSE holiday with
  an open MCX evening session still triggers the login.
- Live promotion remains locked behind the 13Oct2026 P5 gate.
