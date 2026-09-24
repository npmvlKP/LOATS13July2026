# R-08 — Degraded Duplicate OpenAlgo Instance (Shadowed :5000):
# Second Same-Day Recurrence, Live Remediation

**Finding:** the "relaunch fails the WS bind yet keeps running with a
shadowed :5000" pattern (first recorded earlier on 2026-09-24, duplicate
PIDs 34740/36668 per the ops transcript) RECURRED the same day: a
`python app.py` relaunch at 15:32:58 IST failed its :8765 WebSocket bind
fail-closed exactly as designed, but survived as a half-alive instance
holding a second, shadowed :5000 Flask listener.

**Status:** REMEDIATED live (duplicate killed, topology re-verified);
tracked as RISK-REGISTER R-08 with the fix candidate deferred to the
30Sep ops-review window (ADR-0016 mid-span freeze discipline).

## Evidence (2026-09-24, all times IST; this session, tool-scraped)

- 12:06:58 — primary `python app.py` (PID 29116) started; holds
  :5000, :5555 and :8765; healthy all day (the browser SDK session rides
  this process).
- 15:32:58 — duplicate `python app.py` (PID 36592) started. Its own
  startup log (the pasted excerpt, 15:33:14-16) shows the full healthy
  module bring-up ("no open run to recover", "0 strategies, 0 jobs")
  followed by the ERROR: WS port 8765 already in use ->
  `WebSocketProxy.__init__` RuntimeError (websocket_proxy/server.py:65
  via app_integration.py:277) — the SDK-compat fail-closed guard firing
  correctly. The process DID NOT EXIT.
- 15:36 scrape — netstat: TWO LISTENING sockets on 127.0.0.1:5000
  (29116 and 36592); :8765 solely 29116 (HTTP probe answers 426 Upgrade
  Required = WebSocket-only listener, correct); :8001 solely the P5
  forward-test (PID 32968, untouched). HTTP probes: :5000 200 (dual
  binder), :8765 426, :8001 200.
- 15:36 scrape — PID 36592 connection table: ZERO inbound client
  connections (loopback self-pairs only, one client connection to the
  primary's :5555, one outbound idle broker-API session to
  13.232.30.65:443). The duplicate was serving nobody.
- 15:44 remediation — `taskkill /PID 36592 /F`; re-scrape: single
  LISTENING line per port (:5000/:5555/:8765 -> 29116, :8001 -> 32968);
  probes :5000 200, :8765 426, :8001 200. Primary and P5 undisturbed.

## Root cause (code-pinned in the OpenAlgo checkout, not this repo)

Asymmetric bind semantics in the sibling OpenAlgo checkout
(`G:\.OA\OpenAlgo` @ `a51822b4`):

- The :8765 WS path PROBES the port and fails closed (RuntimeError) —
  correct, deliberate (SDK compatibility guard).
- The Flask/socket listener is constructed with socket-reuse options
  (`websocket_proxy/server.py:203-209`, "socket reuse options /
  reuse_port"), which on Windows permits a silent double-bind of :5000.
  SO_REUSEADDR-class reuse on Windows does not fail the second bind the
  way it does on Linux, so the duplicate process survives its own
  fatal-looking error.

Result: a degraded instance that answers HTTP on a shadowed :5000 with
no WS server attached — the `strategies/ltp_example.py` SDK contract
broken on that socket, and two processes sharing one broker login
(order-path ambiguity risk in a live-trading estate). The error text
reads fatal; the process is not. That gap is the defect.

Impact if unremediated: SDK/relay clients can land on the shadowed
listener (intermittent, order-dependent failures that look like flaky
network); duplicate broker sessions race the primary's order path.

## Disposition

- Live: duplicate killed after zero-inbound verification; per-port
  single-listener topology re-verified (above). P5 (:8001) untouched.
- Register: R-08 opened (P2-ops; due 2026-09-30 ops-review window).
- Fix candidates (decide at the window, NOT mid-span):
  (a) OpenAlgo startup pre-flight — bind-or-exit for EVERY port; any
  bind failure is process-fatal (recommended: one fork/exit decision,
  no partial instances);
  (b) runbook-only mitigation — start-script port sweep + kill of stale
  listeners before launch.

## Paste reconciliation note (register discipline)

The same paste that carried this live incident ALSO carried F9-H-05 as
an open High finding — stale: closed by PR #66 `633daae` (merged
2026-09-21), verified at the models (`Field(ge=-1.0, le=1.0)` on both
score fields) + ADR-0017 + the dedicated ensemble/decay/bounds nets.
One paste, both directions of lag: one live incident, one stale
finding. Reconcile against git log / gh / live scrapes BEFORE acting —
the standing rule that this wave re-proved.
