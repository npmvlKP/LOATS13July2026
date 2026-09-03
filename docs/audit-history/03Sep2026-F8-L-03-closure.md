# F8-L-03 Closure — P1 latency evidence scope (03Sep2026)

## Finding (FR8, 01Sep2026)

> **🟢 F8-L-03 — P1 latency evidence is client-side only.** `reports/p1_analyze_latency_*.json`
> (mean 13.45 ms, P95 42.56 ms, 99% pass) measures the in-process analysis loop, not a live
> OpenAlgo round trip. Treat as indicative; re-measure against a live endpoint before
> discharging P1. P3.

## Root cause

`scripts/collect_p1_phase_gate_evidence.py` (v2.0) timed only TA calculation + local SQLite
operations inside its sample loop. No OpenAlgo call existed anywhere in the measured path,
despite the docstring claiming "OpenAlgo API call time (if available)". The resulting JSON
labelled those numbers "Live ANALYZE round-trip latency measurements" with a PASS verdict —
client-side evidence masquerading as live round-trip evidence.

## Remediation (v3.0, this wave)

1. `scripts/collect_p1_phase_gate_evidence.py` — two-scope evidence:
   - **analysis scope** (always): TA + local DB, explicitly labelled
     `measurement_scope: "analysis-scope (client-side only)"`, `p1_discharging: false`.
   - **live scope** (`--live-endpoint`): per-sample read-only
     `AsyncOpenAlgoClient.get_quotes` HTTP round trip to the configured endpoint.
     P1 verdict is taken from this scope only; no live evidence ⇒ verdict
     INDETERMINATE, exit code 2 (was: false PASS, exit 0).
   - Cache-integrity fix: `get_quotes` caches by symbol-digest for 60s, so the probe
     symbol is unique **per sample** (initial per-run uniqueness still let samples
     2..N measure cache hits — median 0.0 ms gave it away; fixed and re-verified:
     median 4.51 ms, p99 16.51 ms against a local mock, 60/60 unique symbols).
2. `scripts/verify_todo25_external.py` (CI-wired via `verify_acceptance_matrix.py`) —
   new mandatory check: evidence must carry `measurement_scope: live-endpoint` **and**
   a `live_evidence` section, else gate compliance FAILS with remediation guidance.
3. `scripts/verify_todo25_final.py` — stage 4 enforces the same scope check.

## Verification evidence (Windows, loatsNEW venv, 03Sep2026)

| Scenario | Result | Exit |
|---|---|---|
| Analysis-scope run (60 samples) | `P1 PHASE-GATE: INDETERMINATE — analysis-scope evidence alone does NOT discharge P1` | 2 |
| Live run, endpoint down | `P1 PHASE-GATE: FAILED (live-endpoint evidence)`, 20/20 connection errors recorded as evidence | 1 |
| Live run vs local mock (60 samples) | `PASSED (live-endpoint evidence)`, 100% pass, realistic latencies (mean 4.78 ms, p99 16.51 ms) | 0 |
| `verify_todo25_external.py` on live-scope evidence | 16/16 checks PASS | 0 |
| `verify_todo25_external.py` on analysis-scope evidence | FAILS with F8-L-03 scope message | 1 |
| ruff / ruff format / isort / flake8 (canonical invocations) | PASS | 0 |
| mypy src/ --strict (pyproject excludes scripts/) | Success: 37 files | 0 |
| bandit on 3 scripts | 0 new findings (only pre-existing B110/B404/B603) | 0 |
| pytest full suite | 1377 passed, 0 failed | 0 |

## Honest status

- The pipeline defect is fixed: client-side numbers can no longer produce a P1 PASS.
- **P1 itself is NOT discharged.** Live verification against the real endpoint
  (03Sep2026, 13:48–13:50 IST) surfaced and fixed a second, deeper client defect:
  the deployment requires `apikey` as a REQUIRED JSON **body** field on every
  POST (`header-only` auth fails schema with 400 on all endpoints), and
  `/quotes` is a SINGLE-symbol `{apikey, exchange, symbol}` contract. The
  client (`src/loats/openalgo.py`) now injects body auth on all POSTs and
  fans out per-symbol quotes while preserving the `{"data": {symbol: ...}}`
  response shape and the 60s result cache. Quote probes now reach the broker
  plugin but return HTTP 500 "API Permission denied: Insufficient permission
  for that call.." for every symbol while `/funds` succeeds with the same key
  — the OpenAlgo API user lacks market-data permission. **P1 discharge is
  blocked on the OpenAlgo deployment granting quote permission to the API
  user** (instance-side setting). Then re-run:
  `loatsNEW/Scripts/python.exe scripts/collect_p1_phase_gate_evidence.py --samples 100 --live-endpoint`
  → exit 0 → `verify_todo25_external.py` exit 0.

Tracked-file impact: none (fresh evidence outputs are gitignored under `reports/*.json`;
the canonical tracked artifact `reports/p1_analyze_latency_20260828_084822.json` is
unchanged and remains the recorded analysis-scope baseline).
