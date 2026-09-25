# R-08 — Degraded Duplicate OpenAlgo Instance (Shadowed :5000):
# Second, Third and Fourth Same-Day Recurrences, Live Remediations

**Finding:** the "relaunch fails the WS bind yet keeps running with a
shadowed :5000" pattern (first recorded earlier on 2026-09-24, duplicate
PIDs 34740/36668 per the ops transcript) RECURRED the same day: a
`python app.py` relaunch at 15:32:58 IST failed its :8765 WebSocket bind
fail-closed exactly as designed, but survived as a half-alive instance
holding a second, shadowed :5000 Flask listener. It RECURRED AGAIN the
same evening: a `uv run app.py` relaunch at
16:31:53 IST produced an identical half-alive duplicate (Continuation 3
below), and a FOURTH time later still: an 18:10:29 IST relaunch from the
same shell window produced an identical duplicate (Continuation 4).

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

- The :8765 WS path PROBES the port and fails closed (RuntimeError,
  `websocket_proxy/server.py:65` via `app_integration.py:277`) —
  correct, deliberate (SDK compatibility guard).
- The :5000 listener is the werkzeug serving stack behind
  `socketio.run(app, ...)` (`app.py:1263`), whose server class sets
  `allow_reuse_address = True` (`werkzeug/serving.py:710`, werkzeug
  3.1.8 in the checkout's venv). On Windows that maps to SO_REUSEADDR,
  which lets a SECOND bind of :5000 succeed silently — no probe, no
  guard, so the duplicate process survives its own fatal-looking
  error. (The `reuse_port=` argument on the :8765 `websockets.serve()`
  at `websocket_proxy/server.py:203-209` is a Windows no-op —
  SO_REUSEPORT does not exist there — and is NOT the :5000 mechanism.)

Result: a degraded instance that answers HTTP on a shadowed :5000 with
no WS server attached — the SDK contract broken on that socket (the
example lives at `examples/python/ltp_example.py` in the current
checkout; the guard's own message at `websocket_proxy/server.py:57`
still names the legacy `strategies/` path), and two processes sharing
one broker login (order-path ambiguity risk in a live-trading estate).
The error text reads fatal; the process is not. That gap is the defect.

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

## Continuation 3 — third same-day recurrence (16:31:53 IST, remediated 17:33)

While the R-08 docs wave was still in review (PR #75), the pattern struck
a THIRD time, post-dating the register's "second occurrence" text. The
pasted startup log excerpt (16:32:02-05) is this duplicate's own log:
healthy module bring-up ("no open run to recover", "0 strategies, 0
jobs", scheduler rebuilt) followed by the :8765 fail-closed
RuntimeError — the same signature as Continuation 2.

- 16:31:53 — duplicate started as a `uv run app.py` wrapper tree:
  uv 29640 -> python 4964 ("G:\.OA\OpenAlgo\.venv\Scripts\python.exe"
  app.py) -> app.py 34316. Root cause of the launch is agent/operator
  relaunch discipline, not auto-respawn: the primary (29116, up since
  12:06:58) was healthy throughout.
- 17:28 scrape — netstat: TWO LISTENING sockets on 127.0.0.1:5000
  (29116 and 34316); :8765 solely 29116; :8001 solely P5 32968. PID
  34316's :5000 socket had ZERO inbound ESTABLISHED connections (all
  three :5000 client sessions rode 29116's socket); its connection
  table was loopback self-pairs, one idle :5555 feed client, and one
  outbound broker session (13.207.98.174:443) — serving nobody.
- 17:33 remediation — the wrapper tree died with a single
  Stop-Process on the app.py root (34316), wrappers 4964/29640 swept;
  taskkill //PID mangling under MSYS bash was worked around with
  PowerShell Stop-Process. Re-scrape: single LISTENING line per port
  (:5000/:5555/:8765 -> 29116; :8001 -> 32968); probes :5000 200,
  :8765 426, :8001 200; no stray `app.py` python processes remain.
  Primary and P5 undisturbed.

Register discipline note: the "second occurrence" text landed in PR #75
before this third event existed; the register chronology row and R-08
section were reconciled in the same wave rather than left lagging.

## Paste reconciliation note (register discipline)

The same paste that carried this live incident ALSO carried F9-H-05 as
an open High finding — stale: closed by PR #66 `633daae` (merged
2026-09-21), verified at the models (`Field(ge=-1.0, le=1.0)` on both
score fields) + ADR-0017 + the dedicated ensemble/decay/bounds nets.
One paste, both directions of lag: one live incident, one stale
finding. Reconcile against git log / gh / live scrapes BEFORE acting —
the standing rule that this wave re-proved.

## Continuation 4 — fourth same-day recurrence (18:10:29 IST, remediated 18:26)

The pattern struck a FOURTH time, from the same interactive PowerShell
window (PID 8244, created 16:31:45) that produced the third: a second
`uv run app.py` relaunch at 18:10:29 IST produced an identical
half-alive duplicate, wrapper tree uv 9912 -> python 15960
("G:\.OA\OpenAlgo\.venv\Scripts\python.exe" app.py) -> app.py 792. The
primary (29116, up since 12:06:58) was healthy throughout; the driver
is relaunch discipline in that shell session, not auto-respawn.

The pasted excerpt (18:11:14-16) is this duplicate's own startup log,
the same signature as Continuations 2 and 3: healthy module bring-up
(websocket connected, order-update WS connected, "no open run to
recover", checkpoint writer, scheduler rebuilt 0 strategies) followed
by the :8765 fail-closed RuntimeError (`websocket_proxy/server.py:65`
via `app_integration.py:277`). New detail: `port_check` waited its
2.0 s grace first ("Port 8765 is still in use on 127.0.0.1 after 2.0 s
wait", 18:11:16,337) before failing closed — the SDK-compat guard
working exactly as designed while the Flask listener silently
double-bound.

- 18:25 scrape — TWO :5000 LISTENING sockets (29116 and 792); :8765
  solely 29116; :8001 solely P5 32968. PID 792's :5000 socket had ZERO
  inbound ESTABLISHED connections: its full socket table was loopback
  self-pairs (ports 18288-18296), one :5555 feed-client connection to
  the primary, and one outbound broker session (13.232.30.65:443).
  All three :5000 client sessions rode 29116's socket (P5 harness
  32968 x2, browser 29704 x1) — the duplicate was serving nobody.
- 18:26 remediation — `taskkill /T /F /PID 9912` swept the wrapper tree
  (792, 15960, 9912 confirmed terminated; the launching shell 8244 was
  deliberately left alone). Re-scrape: single LISTENING line per port
  (:5000/:5555/:8765 -> 29116; :8001 -> 32968); probes :5000 200,
  :8765 426 (WebSocket-only listener, correct), :8001 200. Primary and
  P5 undisturbed.

Paste reconciliation, second instance: the ~18:20 IST paste that
surfaced this incident re-carried the F9-H-05 block as an open High
finding — stale a second time same day. Re-verified live during this
continuation: `Field(ge=-1.0, le=1.0)` bounds on both score fields
(`src/loats/models.py:301,440`), the ensemble/decay implementation in
`src/loats/sentiment.py`, ADR-0017, and 53/53 passes across
`tests/test_sentiment_p3_ensemble_f9h05.py` + `tests/test_sentiment.py`.

Four recurrences in one day, two of them from one operator shell via
`uv run app.py`, strengthen the bind-or-exit pre-flight candidate (fix
candidate (a)): it neutralizes the class at startup regardless of which
shell launches the duplicate. Decision stays at the 30Sep ops-review
window (ADR-0016 mid-span freeze discipline).
