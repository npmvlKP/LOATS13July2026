# 30Sep2026 — R-01 checkpoint wave: ADR-0021, S-14/S-15 riders, R-07/R-08/R-13 window dispositions, benchmark-perf promotion

- **Wave:** the 2026-09-30 P5 checkpoint ops window (ADR-0016 freeze expiry)
- **Decisions:** user-decided at the window (ADR-0016 reserved the branch):
  R-01 → **(b)**; R-13 → **accept-as-designed**; R-08 → **bind-or-exit
  (implemented in-repo)**; R-07 → **pre-run frozen-tree guard**.
- **Snapshot:** branch off `main` @ `ba536f4` (PR #112), tree clean,
  ceiling 506 pre-wave.

## 1. R-01 — cycle-latency budget decision (b), ADR-0021

`docs/adr/0021-cycle-latency-budget-measured-amendment.md` records the
decision: the CMP budget is amended to the measured architecture
(1 Hz cadence / 1 s compliance budget; stage budgets TA 80 / DB 20 /
round-trip 100 ms unchanged). Evidence cited per ADR-0016 §Decision.2:

- 0/26,413 cycles compliant (25Sep evidence pack) + 0/1,278 on the
  gen14 span at the checkpoint probe (`:8001/metrics`, 30Sep ~08:47
  IST: avg 3.84 s, max 11.69 s, kill switch inactive, 5/5 breakers
  healthy — sentiment tracked post-#109);
- every stage the benchmark isolates meets its own budget — the gap IS
  the bounded 8 s producer window (architecture, not regression);
- benchmark-perf green on 15 consecutive `main` runs (25Sep→30Sep,
  `36662564397` latest), advisory evidence per ADR-0016 §Decision.2.

**Enforcement move (single source):** `src/loats/latency_budget.py`
pins `CYCLE_COMPLIANCE_TARGET_SECONDS = 1.0` and
`PRODUCER_BUDGET_WARNING_SECONDS = 0.080` (= the TA stage budget).
Re-derived surfaces (AST-pinned in
`tests/test_latency_budget_pins.py`, RED-proven by mutation):

1. `metrics.record_cycle_time` compliance counter (was `<= 0.1`);
2. `TradingOrchestrator.get_cycle_stats` `target_compliance`
   (was `<= 0.1`);
3. `_record_cycle_time` per-cycle warning (was `> 0.1`);
4. TA producer finally-block (was `> 0.03`);
5. Sentiment producer finally-block (was `> 0.04`);
6. Volatility producer finally-block (was `> 0.03`);
7. Price-action producer finally-block (was `> 0.03`);
8. Options-flow producer finally-block (was `> 0.03`);
9. **NEW (found by this wave's scan — the S-14 census said five
   surfaces and missed these):** the cycle loop's adaptive-sleep floor
   `target_duration = 0.1` — a *seventh* enforcement literal that
   contradicted the documented 1 Hz cadence; now derives from
   `CYCLE_COMPLIANCE_TARGET_SECONDS` (behaviour unchanged in effect:
   cycles average >1 s either way, sleep 0 — the legacy floor was
   already dead, but the literal claimed a budget the system never
   had).

No producer-path or settings change: the 8.0 s window and every
trading setting are untouched (gen14 grades to 13Oct).

## 2. Benchmark-perf promotion (same wave, ADR-0016 §Decision.2)

- ci.yml: job display `name:` renamed
  `benchmark-perf (F9-H-02 prerequisite, advisory)` →
  **`benchmark-perf (F9-H-02 gate)`** — the `name:` IS the
  required-context string; the rename, the green check run on the wave
  PR, and the protection PUT land in ONE wave (the staging pack's
  pinned trap).
- `tests/test_repo_hygiene.py::TestBenchmarkGateWired` extended: the
  promoted name is pinned and the advisory name is refused (RED-able
  by mutating ci.yml).
- CONTRIBUTING.md: the pinned protection contract moves to 11 required
  contexts with the promotion history.
- Protection PUT sequence (executed at merge time): GET + save → PUT
  merge-window config (11 contexts incl. the new name, reviews
  temporarily nulled — the wave PR's old advisory context never
  reports, so the promotion and the review relax must share the
  window) → merge → PUT restored 11-context contract (approving=1,
  dismiss_stale=true, code_owner=false, last_push=false) → GET-verify
  field-by-field on both surfaces.

## 3. S-14 — flipped SUPERSEDED

All enforcement surfaces derive from the single source (§1). Register
row flipped citing ADR-0021; content pins extended in
`tests/test_cmp_supersession_register.py` (ADR-0021 added to the
authority set; S-14 flip pinned). Same-commit rule (ADR-0019) held:
code + register + pins + this record in one PR.

## 4. S-15 — SL-M fixture legs + a latent bug found and fixed

`tests/test_trailing_stop_slm.py` (7 tests): monotonic advance to
SL-M emission (trigger > pre-move stop, SL-M order type, config
persisted), two-advance monotonicity, `ratchet_update` audit row,
Rule-7 `Rule7ModificationLimitError` degradation (stop state restored,
position still ACTIVE/protected, refusal audited, driver continues to
the next position), empty-book silence.

**Latent production bug found by the fixture (the work order's exact
purpose):** `update_trailing_stop` mutates the config dict IN PLACE and
the dict ALIASES `db_position.metadata["trailing_config"]` — the
Rule-7 refusal branch skipped the DB persist but left the advanced
stop (23248.5) in the in-memory Position while the broker (and DB) held
the last successful level (22400.0). A stop-state divergence inside the
cycle window. Fix: the refusal branch now restores
`db_position.metadata["trailing_config"] = old_config` (the pre-move
copy is already in scope). All 70 trailing-suite tests green.

Register row updated: fixture + fix landed; supervised
`enable_trailing_stops` enablement remains the pending leg (a
supervisor touch on gen14+, post-checkpoint by definition).

## 5. R-07 — decision (b): pre-run frozen-tree guard

`TestFixerHooksSpareFrozenEvidence._guard_frozen_trees_or_skip_foreign_hold`
probes the frozen trees with the sweep's own primitive
(`git status --porcelain`) BEFORE any sweep leg and skips fail-visible
on a foreign hold (orphaned mutant sweep / concurrent dirtying process
— the 23Sep incident class); the shipped-config leg re-checks after the
sweep with an exact-banner TOCTOU assertion (a mid-sweep foreign write
voids the green verdict). RED-proven: a pre-dirtied frozen file yields
`SKIPPED ... R-07 frozen-tree guard`; clean tree runs the real sweep
green (3 passed, 15.7 s). Option (a) (process-tree kill) rejected:
kills the wrong child on shared runners.

## 6. R-08 — decision: bind-or-exit, LOATS-side half in-repo

`src/loats/preflight.py::check_duplicate_listener` runs FIRST in
`TradingSystem.initialize` — before any resource initialization, so a
refusal needs no compensating teardown. Identity semantics: a 200 JSON
body on `<openalgo_base_url>/metrics` containing `cycle_time_stats` is
a live LOATS duplicate → `DuplicateListenerError`, boot refused; a
foreign listener (the healthy host), dead endpoint, or timeout is
clear; skipped under ENVIRONMENT=test. Pinned in
`tests/test_preflight_r08.py` (7 tests, faked transport; wiring leg
proves the guard is the first initialize step and nothing below it runs
on refusal). The host-side half (the asymmetric :5000 bind itself)
lives in the OpenAlgo checkout and ships via upstream PR #2047; the
pre-flight makes a relaunched LOATS fail fast against ANY live
duplicate regardless.

## 7. R-13 — decision (c): accept-as-designed

Six occurrences on record (one mid-session), every one fail-closed and
self-healed with zero bad orders — the evidence stand IS the
protection. No code change ships mid-span (gen14 grades to 13Oct).
Option (a) ruled insufficient by the register (mid-session hits);
option (b) rebuild-aware readiness probe deferred to the post-span
producer wave as a candidate alongside R-01 option-(a) decoupling.

## 8. Register actions (same PR)

- `docs/RISK-REGISTER.md`: R-01/R-07/R-08/R-13 rows closed with their
  decision records; R-14 standing confirmation (REGULAR-hours) remains
  open for the 09:15 IST window; R-05 dated 01Oct; R-12 rides 13Oct.
- `docs/CMP-SUPERSESSION-REGISTER.md`: S-01 + S-14 SUPERSEDED (ADR-0021);
  S-15 updated (fixture + fix landed, enablement pending).
- Nets extended in-commit: `tests/test_risk_register_current.py`
  (R-01 closure + evidence pins), `tests/test_cmp_supersession_register.py`
  (ADR-0021 authority + S-14 flip).

## 9. Verification

- New suites: `test_latency_budget_pins.py` 8/8 (RED-proven by
  controlled mutation), `test_preflight_r08.py` 7/7,
  `test_trailing_stop_slm.py` 7/7 (found the aliasing bug).
- Touched nets: risk-register + CMP-register 14/14, repo-hygiene
  frozen-tree + benchmark-gate classes 8/8.
- Full gate battery + ratchet re-pin: see the wave PR checks.

## Ratchet

+7 tracked files: `docs/adr/0021-cycle-latency-budget-measured-amendment.md`,
`src/loats/latency_budget.py`, `src/loats/preflight.py`,
`tests/test_latency_budget_pins.py`, `tests/test_preflight_r08.py`,
`tests/test_trailing_stop_slm.py`, this record — count at staging:
506 + 7 = 513. Ceiling 506 → 513 (history entry 507).
