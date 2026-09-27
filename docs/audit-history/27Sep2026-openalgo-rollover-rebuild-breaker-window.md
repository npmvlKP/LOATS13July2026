# 27Sep2026 Paste Reconciliation — OpenAlgo Daily Rollover + Master-Contract Rebuild Window (Breaker Storm, Fallback-Expiry 404 Burst)

- **Issue ID:** 27Sep rollover/rebuild paste reconciliation · **Category:**
  Host-layer attribution + LOATS fail-closed verification · **Confidence:**
  Certain (live log forensics, source reads, and protection probes run at
  HEAD `10d410f`).
- **Status:** RECORD ONLY for the paste itself — every pasted failure is
  host-layer, transient, or stale. The reconciliation ALSO pins a new
  LOATS-side observation the paste did NOT contain: the 01:16-01:28Z
  (06:46-06:58 IST) breaker storm in LOATS caused by the same host
  window. R-13 opened as a P3-watch item (single occurrence, self-healed,
  hardening decision rides the 30Sep ops window). No production code
  changed by this wave.
- **Snapshot identity:** HEAD `10d410f` (PR #88 merged 2026-09-26), clean
  tree, local `main` == `origin/main`. Main CI run `36263835750` green at
  HEAD. Protection live-read both surfaces this session: classic REST
  `GET /branches/main` -> `protected:true`, exactly the 10 documented
  required contexts, `enforcement_level: everyone`; GraphQL
  `branchProtectionRules` -> `main`: admin-enforced, dismiss-stale,
  1 approving review, strict. P5 run
  `reports/p5_forward_test_20260924_080208.json` LIVE during probes
  (mtime 07:55 IST, `ended_at: null` = correct in-progress state;
  `cycles_completed` 1494, `unhandled_exceptions` 0). `routed_decisions: 0`
  — the R-12 decisional-leg deadline governs (2026-10-08), unchanged.

## 1. Verdict table (paste claim vs live evidence)

| # | Paste claim | Live evidence at HEAD `10d410f` | Verdict |
|---|---|---|---|
| 1 | Strategy Module DB init, order-update adapter deferred ("no login since today's session rollover"), scheduler rebuild 0 strategies (06:46:04-06:46:07) | Host-checkout emitters (`database/strategy_module_db.py`, `websocket_proxy/order_adapter.py`) — grep ZERO hits in LOATS `src/`. The adapter deferral is the designed daily-rollover state: no broker login had occurred yet at 06:46; the adapter started on the 06:47:13 login ("Order-update WS connected: zerodha/kpperumalla") | HOST-LAYER BY DESIGN — informational, not failure |
| 2 | `API Error: Incorrect api_key or access_token` on quotes 06:46:25 and margin/funds 06:46:30; login resume -> redirect to /broker | The stored broker token was stale after the host's daily session rollover (the same 06:46:05 notice). The host's own login flow DETECTED this ("Broker token expired or invalid for kpperumalla: empty funds response"), refused resume, redirected to /broker, and the fresh broker callback connected at 06:47:13 with caches invalidated | HOST-LAYER AUTH ROLLOVER — self-detected, self-recovered by design |
| 3 | `Could not find instrument token for NSE_INDEX:NIFTY` / `Could not find exchange token for NSE_INDEX:INDIA VIX` / `... NIFTY 50` (06:47:40-06:47:42) | Timestamps fall INSIDE the master-contract rebuild window the same paste records: Symtoken table deleted 06:47:17, bulk insert running 06:47:37, completed 06:47:47 (109,485 records), memory cache loaded 06:47:54. These are transient reads of an intentionally-emptied instrument registry during rebuild. Recovery is empirically proven: zero such errors in the stream after the window; the 06:47:48 download-stats line lists `NSE_INDEX` among the 10 processed exchanges. Direct live-DB probe was skipped non-invasively: `db/openalgo.db` is exclusively held by the running host (Permission denied on copy) | HOST-LAYER REBUILD-WINDOW TRANSIENT — bounded, self-healed |
| 4 | Performance Review table (cycle ABANDONED de facto, strike/trail benchmarked-not-gated, F9-H-02/F9-L-01/F9-L-02 flags) | Already reconciled same-day 26Sep by PR #87 (`26Sep2026-performance-review-paste-reconciliation.md`): advisory-by-design gate, S-14/S-15 riders, mechanism corrections pinned | ALREADY RECONCILED — no action |
| 5 | "7. Scalability Review" section (419 files, LITE, backpressure) | VERBATIM the 15Sep FR9 forensic report section 7 (`docs/audit-history/15Sep2026-FR9-forensic-review-report.md` line 198). The tree is at 490 tracked files at this HEAD; the section describes 15Sep state | HISTORICAL RE-SLICE — stale, no action |
| 6 | "8. Reliability Review" section — "**Open:** IV-rank saturation (F9-C-01), sentiment producer death (F9-H-03), P5 evidence divergence (F9-C-02), unchained audit (F9-M-01)" | VERBATIM the 15Sep FR9 report section 8 (same file, line 202). All four are closed at HEAD: F9-C-01 RESTORED (register S-02; loud `insufficient_history` live in `src/loats/rules.py`, legacy silent `return 0.5` grep-empty), F9-H-03 CLOSED (20Sep verification + BG-1 close-out record), F9-C-02 SUPERSEDED (register S-05, ADR-006 Amendment 7), F9-M-01 RESTORED (register S-13; `previous_hash` chain live in `src/loats/database.py`, PR #54) | STALE — all four closed upstream; verdict table per finding |

## 2. The 27Sep breaker-window class — LOATS-side forensics (new pin)

The paste contained only the HOST side. The LOATS log shows what the same
window did to the trading system, and it is the first occurrence of this
class (identical greps over 24/25/26Sep: zero `OPENED after`, zero
global-open refusals, zero no-strikes 404s):

- 01:16:44Z: first error — `Trading cycle error: Circuit breaker
  'openalgo' is open` — the global breaker had already tripped on the
  rollover auth gap (06:46 IST), BEFORE the host login at 06:47:13.
- 01:16:45-01:21:16Z: 351 `Failed to get quotes: global circuit breaker
  open` refusals — the fail-closed design refusing every market-data
  fetch while the broker token was invalid.
- 01:18-01:24Z: 35 per-source breaker OPENED events (ta, volatility,
  price_action, options_flow) cycling OPEN -> HALF_OPEN -> CLOSED as the
  master-contract rebuild emptied and refilled the instrument registry.
- 102 `404 No strikes found for NIFTY expiring 04OCT26` errors
  (01:18:59-01:27:18Z). Root cause chain, source-verified at this HEAD:
  the orchestrator's breaker-guarded chain fetch
  (`orchestrator.py:378-411`) could not resolve a listed expiry while
  the host registry was empty/breaker-open, so
  `_resolve_expiry_date` fell back to the computed hint
  `_option_chain_expiry_date(7)` (`openalgo.py:250-262`,
  fallback selection `openalgo.py:301-309`) = 2026-09-27 + 7 days =
  04OCT26 — a Sunday, not a listed NIFTY expiry (real weekly expiry
  Tue 29Sep) — a guaranteed 404 per fetch. The 404 tail persisted ~9
  minutes past the rebuild's 06:47:47 completion because each failed
  `/expiry` resolution kept re-emitting the hint until the global
  breaker closed and `/expiry` succeeded; the resolved-expiry cache
  (`openalgo.py:1195-1200`) only stores on success, by design.
- Full recovery: per-source `CLOSED after recovery` events through
  01:28:40Z; ZERO breaker events in the log after 01:29Z.
- P5 span untouched: `unhandled_exceptions: 0` across the window; the
  graded span's counters carry no storm residue.

Classification: fail-closed worked exactly as designed — every layer
(host auth rollover, global breaker, per-source breakers, loud 404s)
refused to fabricate data during a ~12-minute host maintenance window.
No decision was made, no order was routed, the audit trail and P5
evidence are clean. The finding is NOT a defect: it is a documented
consequence of running a Sunday 06:46 IST host rollover + rebuild while
the LOATS scheduler cycles. Hardening candidate (grace/suppress
synthetic cycles across the known rollover window, or a rebuild-aware
readiness probe) is freeze-bound (ADR-0016 mid-span discipline) and
rides the 2026-09-30 ops window alongside the R-08 bind-or-exit
decision. Opened as R-13 (P3-watch, single occurrence).

## 3. Recommended Next Step (unchanged by this paste)

The 2026-09-30 checkpoint wave (R-01) remains the next major work: the
ADR-0016 (a)-vs-(b) decision citing the 25Sep evidence pack, the S-14
(FIVE producer surfaces, one commit) and S-15 riders, the
benchmark-perf context rename BEFORE the 11-context protection PUT, and
the `test_p1_items_carry_the_checkpoint_due_date` extension. R-13
joins R-08 as a 30Sep ops-window decision (watch-only until then);
R-12's 08Oct decisional-leg deadline and R-05's 01Oct shared-venv
rebuild follow on their registered dates.

## 4. Live-system observations during probes

- P5 span LIVE (mtime 07:55 IST, ended_at null, 1494 cycles, 0
  unhandled exceptions, 5 restarts — supervisor continuity intact).
  `routed_decisions: 0` — R-12 continues; the 30Sep decision governs.
- Protection: clean field-by-field read-back on BOTH surfaces this
  session (classic REST contexts+enforcement AND the GraphQL
  review/strict fields) — the first watch recorded in this family that
  cites both surfaces in one read-back.
- The decisional funnel produced zero log-visible outcomes today
  (0 trade-decision/routing events, grep-verified) — consistent with
  the global breaker refusing every market-data fetch through the
  storm window; no signal-batch rows were written.
- `db/openalgo.db` live probe skipped: the running host holds an
  exclusive handle (Permission denied); recovery was proven via the
  host's own log stream instead (zero token errors after the rebuild
  window).
