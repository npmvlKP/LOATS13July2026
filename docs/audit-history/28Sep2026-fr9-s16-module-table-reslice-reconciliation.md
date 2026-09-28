# 28Sep2026 — FR9 re-slice family: §16 module-table member (first §16 consumption)

## 1. Member identification

This is the FIFTEENTH member of the 27Sep FR9 paste family and the seventh
standalone tracked reconciliation record. Its composition is two sections:
the archive's §16 Module-by-Module Review (14 module rows) — the FIRST member
to re-slice §16 — followed by a verbatim repeat of §15 Production Readiness
Assessment (dispositioned by the prod-readiness record, PR #96). No router
paragraph this time. Per the pool-arithmetic rule the §16 half needs fresh
per-claim verdicts; the §15 half collapses onto the #96 dispositions.

## 2. Containment probe (normalized per-line)

Normalization per protocol: `*`/`_`/`|`/tabs → spaces, ordered-list markers
stripped, whitespace runs collapsed, per-LINE comparison only.

| Paste block | Lines | Contained | Archive scope |
|---|---|---|---|
| §16 Module-by-Module Review | 15 | **15/15** | 15Sep source §16 (lines 273-290) |
| §15 Production Readiness Assessment | 12 | **12/12** | 15Sep source lines 255-271 (via the #96 record's per-claim dispositions) |

## 3. §16 per-claim verdicts at HEAD `e4e110e` (probe time 2026-09-28T10:34Z)

Grading key: the archive row's finding citation is checked against the
finding's LIVE disposition, not against the archive's age. Five of the eight
distinct findings cited in the table are closed-and-verified live below; the
still-open ones (R-01 latency decision, R-14 watch) keep their register
state — the rows citing them are accurate-as-of-archive and stale only where
they cite a closed finding as open.

| Row | Paste claim | Live evidence at `e4e110e` | Verdict |
|---|---|---|---|
| trailing_stop.py 93.2 % ✅, default OFF (F9-L-02) | `config/settings.py:137-141` — `enable_trailing_stops: bool = Field(False, ...)` with the "default False = risk-off" comment; cycle gate at `orchestrator.py:1809` | CONFIRMED |
| options.py / options_math.py ✅ (ADR-0004) | ADR `docs/adr/0004-vollib-handrolled-migration.md` present; hand-rolled BS comment at `options.py:16-17`; no vollib import anywhere in `src/` | CONFIRMED |
| trade_decision.py ✅ routing/queue/persistence | Module live; routing success/disabled/error + queue lifecycle pinned in `tests/test_trade_decision.py`; no open finding cited | CONFIRMED |
| orchestrator.py 🟠 5 producers; 8 s window (F9-H-02); as_of_date not passed (F9-H-04) | Producer-gather design intact (`orchestrator.py:586`); F9-H-02/R-01 decision still OPEN per register (due 30Sep) — accurate. F9-H-04 STALE: the call site now passes the snapshot key — `orchestrator.py:620 await self._execute_cmp_strategy(as_of_date=None)` into the callee at `:1223` whose None-default resolves the UTC-date-under-IST-offset snapshot semantic (F9-C-01/TODO-1 contract) | PARTIAL — F9-H-04 citation contradicted, closed upstream |
| rules.py 🔴 IV-rank math broken (F9-C-01) | Two-sided grep: `insufficient_history` sentinel live at `rules.py:513`; legacy `return 0.5` — zero hits | CONTRADICTED — RESTORED upstream |
| strength.py 🟠 thresholds off-spec (F9-H-01) | Conformance pins live: `strength.py:115` (TA weight 0.4), `:130` (opposition 0.4, LazySettings-resolved); legacy 0.5 tier documented dead-by-construction at `:297-298`; supersession S-03 RESTORED (PRs #62/#63) | CONTRADICTED — RESTORED upstream |
| sentiment.py 🔴 producer dead in prod (F9-H-03); P3 spec absent (F9-H-05) | F9-H-03 closed 20Sep (liveness + detached cache-only refresh, PR #65); F9-H-05 ensemble delivered (PR #66, `633daae`). Current live state is R-14 P2-watch (untimed newspaper4k downloads starve the 8 s window; fix rides 30Sep) — a DIFFERENT mechanism than "dead in prod" | STALE — superseded by R-14 watch |
| strike_selection.py 🟡 no 2SD (F9-M-05) | `strike_selection.py:30-32` — `DELTA_BAND_LOW/HIGH = 0.50/0.60`, `STD_DEVIATION_MULTIPLE = 2.0` under the CMP S4 spec comment; supersession S-06 RESTORED (PR #55) | CONTRADICTED — RESTORED upstream |
| backtest_sanity.py ✅ weekly driver, floors restored | Module live; no open finding cited | CONFIRMED |
| scheduler.py ✅ single engine (ADR-0005) | `docs/adr/0005-scheduler-signal-engine-retirement.md` present | CONFIRMED |
| alerts.py ✅ /kill //resume gated | Kill-switch gating live-probed (OPS row of the §15 table, #96 record); no open finding cited | CONFIRMED |
| database.py (+async_additions) 🟡 chaining absent (F9-M-01) | `previous_hash` chain live in `database.py`, `database_async_additions.py`, `models.py`; 17Sep repair + F9-M-01-R1 wave landed; deviation bookkeeping lives in the supersession register (S-13 RESTORED), not absent code | CONTRADICTED — chaining present |
| utils/per_source_breakers.py 100 % ✅ (F8-L-01 closed) | File live at `src/loats/utils/per_source_breakers.py`; F8-L-01 closed with the masked second defect fixed under `fix/perf-gate-success-rate` (R-09-adjacent, pinned in `tests/test_performance_analyzer.py`) | CONFIRMED |
| ta.py (numba) 86 % ✅ | Module live; numba rationale recorded (ADR-0003 per §17) | CONFIRMED |

Score: 8 CONFIRMED, 1 PARTIAL (F9-H-04 citation stale), 4 rows citing
findings restored/closed upstream (F9-C-01, F9-H-01, F9-M-05, F9-M-01) +
1 superseded (F9-H-03 → R-14). No NEW finding. The register remains the
authoritative state for the two OPEN citations (R-01 30Sep, R-14 30Sep).

## 4. §15 carry-over

The §15 repeat is containment-identical to the section the #96 record
dispositioned per-claim (12/12). Code-state deltas between that record's
HEAD (`422b022`) and this wave's base (`e4e110e`) are docs and ratchet
re-pins only — the dispositions carry over untouched, including the
NOT-READY verdict, which STANDS.

## 5. Pool arithmetic

§16 is now consumed. Unre-sliced pool after this member: **§1-8, §17-21,
Appendix**. A further member carrying only §15/§16/§14/§13/§11/§12 repeats
collapses whole under this record + the #95-#98 chain.
