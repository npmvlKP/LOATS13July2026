# P5 Run 140341 — Opening-Session AUTH OUTAGE (2026-09-17)

**Severity:** HIGH (operator action required) — first morning of the
fresh 14-day evidence run is collecting no decisional evidence.
**RESOLVED 17Sep 18:48 IST** — see the closing entry at the end of this
record.

## Timeline (IST, UTC+5:30)

- 19:31 IST 16Sep: run 150243 honestly ENDED at operator request
  (lifetime 5,503 cycles; final counters 70/0/0, divergence 0 — best
  day of the run was its last).
- 19:33 IST 16Sep: replacement run `p5_forward_test_20260916_140341`
  started (evidence-preserved re-run per the NO-GO recommendation);
  route-watch re-pointed 19:36 IST.
- 05:00 IST 17Sep: OpenAlgo instance restarted (fresh PIDs 2184/23840)
  by the automation's OpenAlgo-restart wave.
- 07:49 IST (02:19Z): `openalgo` breaker OPENED after 146 consecutive
  failures; all four source breakers followed. Failure signature:
  **HTTP 500 "Error fetching quotes: API Error: Incorrect `api_key`
  or `access_token`"** (170 occurrences, loats.openalgo logger) —
  OpenAlgo's broker session/token was invalidated by the restart.
- 07:49–09:05+ IST: breaker cycled OPEN/HALF_OPEN continuously —
  1,025 OPENED events by 09:00 (consecutive-failure count climbed
  146 → 218). LOATS behavior correct throughout: degraded fetch,
  breaker protection, zero crashes, zero in-session opens before
  the bell.
- 09:05 IST probes: `GET /` HTTP 200 (first probe 1.9–2.5 s cold,
  second 25 ms) — host CPU 6%, OpenAlgo process healthy; the outage
  is AUTH-ONLY on the authenticated quotes path, not connectivity.

## Root cause

OpenAlgo's 05:00 IST restart discarded its broker session. Every
subsequent LOATS quotes request is rejected upstream with an auth
error. **Fix is operator-side: re-authenticate the OpenAlgo ↔ broker
session (broker login / access-token regeneration in the OpenAlgo UI),
then verify one quotes call succeeds.** No LOATS-side change is
warranted; breaker isolation performed to spec.

## Impact on the P5 gate

- Run 140341 span 0.5d; the morning window (09:15+) produced routing
  of nothing while auth was down. First decisional evidence of the
  new run is deferred until re-auth + market hours.
- The 14-day clock keeps running; per the 16Sep restart records the
  gate mark is 30 Sep 20:33 IST with the grading checkpoint at 21:00.
  Days lost to auth outages erode the decisional-evidence density the
  gate grades — re-auth urgency is about evidence density, not the
  clock.
- 150243's closing state (70/70 provenance-locked successes on 16Sep)
  is intact in its own run JSON as context for the grader.

## Escalation — outage crossed into trading hours (09:30 IST tick)

- 09:15 IST session open passed with the auth outage unresolved: first
  IN-SESSION breaker OPENED events of run 140341 fired at 09:25–09:30
  IST (70 by the 09:30 watch tick; 75 by 09:31 direct count). The
  breaker has NEVER reached CLOSED since 07:49 — every HALF_OPEN probe
  fails with the same auth error and re-opens.
- 09:31 IST: last auth error 46 s before check (still live); supervisor
  unharmed — cycles 12,014 accruing, 0 unhandled exceptions, kill
  switch off, run-log sample 54 s old. The isolation layer is carrying
  the entire load; the exposure is 100% evidence loss, zero safety
  exposure.
- Market impact window so far: ~1h45m of the regular session (first
  15m pre-open, remainder in-session) producing no routable quotes and
  therefore no decisional evidence for the new run.

Standing request unchanged and now urgent: **operator re-auth of the
OpenAlgo ↔ broker session**. Verification signature once done: auth
errors stop, breaker HALF_OPEN → CLOSED within one recovery window,
counters begin accruing on the next decision cycle.

---

## Follow-up addendum (F9-C-02 wave, 2026-09-17 ~15:05 IST)

**Relocation.** This record moved from `reports/p5_auth_outage_20260917.md`
(untracked there, zero `.gitignore` coverage — the same re-arm vector
that tripped the 430-vs-429 repo-hygiene ceiling on 17Sep) into
`docs/audit-history/` per the artifact discipline: the dated
audit-history record is the evidence of record, and the grader's outage
registry cites this path.

**State at addendum time — outage STILL LIVE.** Last observed auth
failure `2026-09-17T09:31:23Z` (15:01:23 IST); `openalgo` breaker still
open-cycling; supervisor healthy (26k+ cycles, 0 unhandled exceptions,
kill switch off). The window is therefore registered OPEN-ENDED in the
grader (`DOCUMENTED_OUTAGE_WINDOWS`, end `None`); this addendum's
closing entry pins the end stamp once re-auth is verified.

**Span-validity reflection (grader change, this wave).** Forensics
before the change: run `20260916_140341`'s routing provenance is CLEAN
through the outage — zero `routing_enabled:false` ROUTE rows in-span
(DB probe), `routing_divergence_detected: 0`, counters 0/0/0 because the
breaker carried the load. The outage is therefore NOT contamination
(a VOID would mis-grade a clean run); it is a decisional-evidence hole.
`verify_p5_forward_test` gained the annotation-only
`DOCUMENTED_OUTAGE_WINDOWS` registry (mirror of
`CONTAMINATION_WINDOWS`): overlapping runs carry a
`Grade.annotations` NOTE in the validator CLI — non-grading, verdict
untouched. Pinned RED-first by `tests/test_p5_f9c02_outage_window.py`
(10 failed / 2 passed on the initial 12 pins pre-fix; the 13th pin —
open-ended-window disclosure — added mid-wave with the live-outage
re-probe; full set green after the validator change, legacy grader
suites green).

### Outage closed (17 Sep 2026 18:48 IST)

- Operator re-auth: Zerodha broker session re-established 18:47:50 IST
  (OpenAlgo `auth_utils`: "User kpperumalla logged in successfully with
  broker zerodha"; session login time 18:47:50.414616+05:30).
- Last auth failure stamp (UTC): `2026-09-17T13:17:29.614205Z`
  (18:47:29 IST — 21 s before the re-auth).
- Breaker recovery: `openalgo` HALF_OPEN -> CLOSED at
  `2026-09-17T13:18:32.842597Z` (18:48:32 IST) — first CLOSED since the
  07:49 IST trip, closing 3 successes inside one 60 s recovery window;
  zero OPENED events after recovery (verified through 18:55 IST).
- First post-re-auth decisional evidence: deferred to the next market
  session — the breaker closed at 18:48 IST, 3 h 18 m after the 15:30 IST
  close, so no quotes/decision cycle could run (DB probe: run 140341 has
  zero in-span ROUTE rows; counters remain 0/0/0, supervisor unharmed).
  First counter increments expected 18Sep ~09:15 IST; note that Zerodha
  access tokens expire daily, so each morning needs a fresh broker login
  in the OpenAlgo UI before session open.
- Grader end stamp pinned: `2026-09-17T13:18:32+00:00` in
  `DOCUMENTED_OUTAGE_WINDOWS` (scripts/verify_p5_forward_test.py) with
  the registry pin updated in the same commit
  (tests/test_p5_f9c02_outage_window.py) — window start untouched.
