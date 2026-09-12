# P3 Carried-Set Round — F8-L-01…06 + F8-M-07 Re-Derivation (2026-09-12)

**Date:** 2026-09-12 (Asia/Calcutta, Saturday). **Base:** `main` @ `c99a259`
(merge of PR #24, weekend-session + audited-rejections wave). **Tree before
wave:** clean, 408/408 tracked files. **Trigger:** the P3 carried set
(F8-L-01 through F8-L-06 plus F8-M-07) was handed forward for a live
re-derivation round. **Method:** every disposition re-established against
the live tree and live endpoints at HEAD — external verifiers executed
fresh, branch protection read back from the API, live P1 round trips and
live RSS re-validation run against the configured production endpoints.
Record narrative was treated as claims, not facts.

## Per-item verdicts at HEAD

| Item | Disposition at HEAD | Live evidence (2026-09-12) |
| --- | --- | --- |
| Per-source breakers (F8-L-01) | CLOSED, no drift | `scripts/verify_carried_set_external.py` 31/31 GREEN at HEAD (registry serves a distinct breaker per active producer — 5 active of 7 members, distinct=True); isolation net `tests/test_per_source_breakers.py` and the dedicated ANALYZER_CIRCUIT_BREAKER (11Sep wave) unchanged. |
| `as_of_date` convention (F8-L-02, CMP Rule 8) | CLOSED, no drift | Verifier chain PASS: implementation spans `backtest_sanity.py`, `database.py`, `database_async_additions.py`, `models.py`, `orchestrator.py`, `trade_decision.py`; `TradeDecision` model field, engine + orchestrator parameters, persisted column, and the zero-`date.today()` invariant all hold at HEAD. |
| Live P1 re-measurement (F8-L-03) | DISCHARGED 04Sep; **live re-measure FAILED today — see finding below** | 240 fresh live round trips (100 TCS + 100 TCS + 40 INFY) to `http://127.0.0.1:5000`, 240/240 HTTP-successful, 0 transport failures — but gate compliance 20% / 22% / 20% (mean 235.65 / 399.01 / 264.74 ms; median up to 373 ms) versus the tracked artifact's 57.62 ms mean / 100% compliance. |
| Probe debris (F8-L-04) | DISCHARGED at HEAD + **new ref-form residue purged this wave** | Probe commits `44f91515` / `0576eb36` remain absent (objects unresolvable — GC'd); branch protection re-read live from the API: approvals=1, contexts=10, strict=true, enforce_admins=true. New finding: the debris branches below. |
| bloombergquint feed (F8-L-05) | CLOSED, live leg now covered | `settings.rss_feeds` default has no bloombergquint and 3 valid sources; `DEFUNCT_FEED_MARKER` guard intact; recorded manifest 3/3 valid AND `scripts/validate_rss_feeds.py --check` live re-validation 3/3 PASS (economictimes, moneycontrol, livemint) — the first live-leg proof recorded on this register. |
| nltk warning (F8-L-06) | CLOSED, waiver current | `LOATS_SUPPRESS_NLTK_WARNING` knob shipped; ADR-0010 waiver re-verified live this morning by the R1 discharge (nltk 3.10.3 still latest, safety 3.8.1 still pins `nltk>=3.9`); verifier surfaces green at HEAD. |
| VIX constant (F8-M-07) | CLOSED, no drift | `scripts/verify_f8m02_m07_external.py` 19/19 GREEN at HEAD: `vix_gate_threshold=15.0` in `config/settings.py`, zero inline threshold literals in `rules.py`, directional behavior preserved (below → BUY only, above → SELL only), unknown VIX blocks both directions (fail-safe). |

**Carried-set verdict: seven of eight re-verified GREEN at HEAD; F8-L-03's
underlying live-latency condition is NOT reproducible against today's
endpoint state (finding 1); F8-L-04's debris class had one surviving
ref-form residue (finding 2, purged this wave).**

## Finding 1 — live P1 latency degraded vs the discharge artifact (STANDING RISK, operator action)

Three independent live runs against the configured endpoint
(`http://127.0.0.1:5000`, local OpenAlgo instance, `python.exe` PID 36504,
~82 MB RSS) on Saturday 2026-09-12 ~13:55–14:05 IST:

| Run | Symbol | Samples | ok | Mean | Median | P95 | Gate pass |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | TCS | 100 | 100 | 235.65 ms | 280.88 ms | 364.35 ms | 20% |
| 2 | TCS | 100 | 100 | 399.01 ms | 373.33 ms | 947.15 ms | 22% |
| 3 | INFY | 40 | 40 | 264.74 ms | 324.38 ms | 433.70 ms | 20% |

Discriminators observed: symbol-independent (TCS ≈ INFY), transport-clean
(240/240 successes — this is latency, not availability), whole-endpoint
(median ≈ 300 ms floor with a ~1 s tail, where the 04Sep artifact showed a
57.62 ms mean). The degradation lives in the OpenAlgo instance or its
broker upstream, not in this repository — no LOATS code path sits inside
the measured round trip (`POST /api/v1/quotes` probe, read-only).

Classification: the 04Sep discharge artifact remains the valid
evidence-of-record FOR 2026-09-04 (its internal claims are intact and
still verifier-pinned); it no longer describes the endpoint's current
behavior. P1's live gate would fail if re-run in today's conditions.

Standing risk raised (top priority for the operator): inspect/restart the
local OpenAlgo instance (PID 36504 at measurement time; candidates:
accumulated per-request state in the long-running process, broker-upstream
Saturday behavior, master-contract handling per request), then re-run
`python scripts/collect_p1_phase_gate_evidence.py --samples 100
--live-endpoint --symbol TCS` on Monday's trading session to establish
whether the 04Sep profile recovers off-weekend. Harness note: the default
probe symbol `TEST` is not in OpenAlgo's master contracts (0/100 with
symbol-not-found); the harness diagnosis already prescribes a real symbol.

## Finding 2 — debris branches `production-hardening` / `test-hooks` (purged this wave)

F8-L-04 removed the probe COMMITS; the branch REFS that pin the same
junk lineage survived on the local clone AND on origin
(`refs/heads/production-hardening` @ `699f501`, `refs/heads/test-hooks`
@ `c446a31`, both dated 2026-08-25, neither an ancestor of `main`):
28 and 29 unique commits of hook-testing debris (`test_file*.txt`),
report dumps (`bandit*`, `gitleaks*`, `ruff*`, `mypy-report/html/*`,
`safety-report.json`, `pip-audit-report.json`), and tool-scratch trees
(`.clinerules/`, `.opencode/`, `.harness-memory/memory.sqlite`).

Deletion safety was proven before any ref was touched:

* Zero files exist branch-side that main lacks (`git diff main <branch>
  --name-status` A-status set contains only the junk classes above — the
  only non-junk names, e.g. `src/loats/var_engine.py`, differ in content
  only because main's six subsequent waves rewrote them; the merge-base
  diff confirms the branch side is the stale ancestor generation).
* The branches' last real content (commit-msg hook docs, ci.yml edit) was
  superseded by the 06Sep–12Sep CI waves on main.

Correction executed: both refs deleted locally and on origin. The debris
objects become unreachable; no tracked file changes (net tracked delta of
this wave: +1, this record). Root-cause note for the register: debris
classes must be swept at REF level, not only at commit level — a purged
commit survives indefinitely behind any ref that pins it, on every clone
that has fetched it.

## Finding 3 — P1 evidence selection was nondeterministic (found and fixed this wave)

Running the live harness honestly FAILED the HC-29 gate 90 seconds later:
`tests/test_todo25_verifier_gates.py::TestHC29Registration::test_hc29_runs_and_passes`
went red because both TODO-25 verifiers selected their evidence file with
a newest-on-disk glob (`sorted(reports.glob(...), reverse=True)[0]`), and
this wave's gitignored run artifacts (2026-09-12_*) were newer than the
tracked evidence-of-record. The gate verdict therefore depended on
untracked scratch state: CI only ever passed because a fresh checkout
happens to hold exactly one matching file. The same wave's local re-run
would have flipped the verdict invisibly — the exact silent-drift class
F8-M-03 exists to catch, found here by a real operator action.

Fix (this wave, RED-first): `select_p1_evidence_file()` added to both
`scripts/verify_todo25_final.py` and `scripts/verify_todo25_external.py`
— the tracked evidence-of-record
(`p1_analyze_latency_20260904_040609.json`, the name both hygiene
allowlists already pin) always wins; newest-on-disk is fallback only.
Pinned by `tests/test_todo25_verifier_gates.py::TestP1EvidenceSelectionDeterminism`
(5 tests, RED on the pre-fix tree, GREEN post-fix, including the
canonical-beats-newer and absent-canonical fallback legs). Post-fix,
HC-29 and the Stage-3 pipeline pass end-to-end with the four newer
2026-09-12 run artifacts still on disk.

## Verification

* `scripts/verify_carried_set_external.py` → 31/31 verified, rc=0 (HEAD).
* `scripts/verify_f8m02_m07_external.py` → VERIFIED: 19/19, rc=0 (HEAD),
  including the m02 RED/GREEN mutation pair re-proven in-suite.
* `scripts/validate_rss_feeds.py --check` → recorded 3/3 + live 3/3, rc=0.
* Live P1 harness: 3 runs as tabulated above (honest FAIL recorded — the
  gate evidence for today is the failure itself, not a pass).
* Tracked-file ratchet: 408 → 409 (+1, this record) per the re-pin
  protocol; branch deletions do not move the count.

## Disposition

The carried set remains eight of eight CLOSED/DISCHARGED at HEAD, now
backed by same-day live evidence on every externally observable item.
Finding 1 transfers to the operator as the top standing risk (OpenAlgo
instance health + Monday re-measurement); Finding 2 is closed by this
wave's ref purge.

## Same-day addendum — Finding 1 RESOLVED after instance restart (13:29 IST)

The operator restarted the OpenAlgo instance before the re-measurement:
old PID 36504 no longer existed; a new `python.exe` (PID 30492) was
LISTENING on `127.0.0.1:5000` (netstat, `GET /` → HTTP 200). The standing
risk was re-measured the same day instead of waiting for Monday:

| Run | Symbol | Samples | ok | Mean | Median | P95 | Gate pass |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | TEST (harness default) | 40 | 0 | 24.97 ms | 23.02 ms | 44.10 ms | 0% — symbol-not-found, expected |
| 5 | TCS | 100 | 100 | 67.36 ms | 63.70 ms | 89.54 ms | **98% — PASS** |

Run 4 was the pre-restart artifact of this addendum wave's own harness
invocation: the default probe symbol `TEST` is not in master contracts
(0/40, HTTP 400), exactly as the Finding 1 harness note predicted — but
its transport timings (25 ms mean even on rejected requests) already
signalled a recovered instance. Run 5 is the like-for-like TCS
re-measurement: `scripts/collect_p1_phase_gate_evidence.py --live-endpoint
--samples 100 --symbol TCS` → **P1 PHASE-GATE: PASSED (98.00% ≥ 80%)**,
exit 0, evidence `reports/p1_analyze_latency_20260912_132927.json`
(gitignored run artifact; the tracked evidence-of-record for 04Sep is
unchanged and remains pinned by `select_p1_evidence_file()`).

Disposition update: the degradation profile (235–399 ms mean, 20–22%
gate) is attributable to the long-running instance process and did not
survive its restart — mean 67.36 ms / 98% is back inside the 04Sep
profile (57.62 ms / 100%). Finding 1's standing risk is DOWNGRADED:
Monday's session re-run becomes a routine live-session confirmation, not
a risk-holding action.

Hygiene incident recorded in the same wave: the manual `pip-audit
--format json --output pip_audit_*.json` scratch files from this morning
were found STAGED (tracked count 409 → 411) and failed the repo-hygiene
ceiling. Root-cause fix in `.gitignore` (root-anchored `/pip_audit_*.json`
and `/pip-audit_*.json`, both spellings, matching the 09Sep
`gitleaks_session.json` precedent); the staged copies were unstaged and
removed. Net tracked delta of this addendum: 0 (409 = ceiling).
