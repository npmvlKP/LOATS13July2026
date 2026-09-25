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

## Continuation (re-landed 23 Sep): 21–23 Sep OpenAlgo process deaths

An earlier 21Sep continuation documenting that day's outage was dropped
by the `3d70824` record rewrite (17:36 IST 21Sep); re-landed here with
the 23Sep evidence, which converts the incident into a **repeat defect
with a root-cause lead**.

### 21 Sep (digest-verified facts)

- ~07:15 IST: OpenAlgo died silently (no WER record; stdout of the
  pre-death instance ended mid-traffic, healthy). Transport class:
  conn-refused, no listener on 5000. LOATS auth was valid (06:23 OAuth).
- Three uncoordinated restart actors (automation 06:23, manual 10:40,
  automation 12:23:28) each voided the broker session → operator
  re-logins at 11:30 and ~15:4x. 180 in-session breaker opens.
- Decisional evidence 53/53 provenance-locked; supervisor unharmed.

### 23 Sep (fresh forensics)

- 08:38:41 IST: automation instance (PID 24900) live; 08:40:15 operator
  OAuth; breakers CLOSED 08:41:30 — cleanest setup of the span.
- **09:41:47 IST: died silently again.** `log/errors.jsonl` (capped at
  1,000 lines — rotation destroys death evidence) ends mid-traffic, no
  fatal entry; no WER record. **Prime suspect captured pre-death**:
  `sqlite3.OperationalError: database is locked` (08:40:36/47) on the
  analyzer-mode toggle — SQLite write contention, consistent with the
  known dual-instance co-existence sharing `openalgo.db`.
- Automation restart loop restored the listener ~09:45 (PID 17452);
  session voided again (second operator re-login before 10:00 IST).
- LOATS side: 60 in-session-ish breaker opens around the death window,
  all recovered; supervisor unharmed (restarts 11, zero exceptions).

### Wave request (root-cause lead in hand)

1. **Single instance, enforced**: kill-with-notify secondaries; restart
   loop takes a global advisory lock so manual/automated restarts
   cannot interleave.
2. **DB contention fix**: enable WAL + busy_timeout on `openalgo.db`
   (or move to a server DB) — multi-process access is the leading death
   hypothesis.
3. **Evidence retention**: raise/remove the 1,000-line `errors.jsonl`
   cap; capture stdout on automation-managed instances (proven workable
   on 21Sep).
4. **Root-cause the silence**: unhandled exception in a non-logging
   thread is the likely mechanism; a faulthandler dump would confirm.
5. **Window-registry follow-up for the F9-C-02 owner**: verify and pin
   21Sep + 23Sep in-session breaker windows (21Sep 10:08–10:37 and
   12:14–12:27 IST clusters; 23Sep ~09:42–09:45 cluster) as
   annotation-only outage windows, mirroring the 17Sep precedent.

## Continuation 3 (24 Sep): token wall erratum — the invalidation is progressive

**The week's pattern resolves into one mechanism.** On 24 Sep the
operator re-logged at 12:10:00 IST (login id 93, oauth zerodha) — and
the session **survived** an OpenAlgo restart afterward (12:29 manual
restart), with quotes succeeding through the full chain at 12:35 IST
(`x-api-key` + body-key probe, HTTP 200, live RELIANCE quote). Access
tokens therefore persist in `openalgo.db` across restarts; restarts
alone never voided anything.

What voided sessions on 17, 21 and 24 Sep was **time of day** — and the
24 Sep evidence shows the invalidation is **progressive, not
instantaneous**. Verified sequence on 24 Sep: 05:20:17 IST — first
quotes-permission failures seen LOATS-side (`API Error 500: API
Permission denied: Insufficient permission for that call`; breaker
OPEN 05:20:18, log anchor `logs/loats.log.5` line 52740); 05:33:40-50
— OpenAlgo-side historical-data permission denials and the websocket
goodbye + 403 handshake (`G:/.OA/OpenAlgo/log/errors.jsonl`); 06:35:14
— first explicit quotes rejection `Incorrect api_key or access_token`
in the OpenAlgo auth-layer log (the stage the first draft pinned as
THE death). The 12:08 IST order-WS 403 is the same dead session's
downstream symptom. Across the week the quotes-auth stage lands at
06:19-07:49 IST (19-23 Sep: 07:41, 06:38, 06:19, 07:45), consistent
with Zerodha's daily pre-open token wall; the 05:20-05:33
permission-stage precursor was observed only on 24 Sep — that other
days had no supervisor traffic in that window (the 04:50-06:25 restart
wave) is plausible but unverified.

**Operational rule going forward**: treat ANY broker failure from
~05:20 IST as the session entering the daily invalidation. Land the
broker login AFTER the band — on current evidence never before
~08:00 IST — ideally before the 09:15 open so the open is covered; if
the morning is lost, a mid-day re-login covers the remainder of the
session (24 Sep 12:10 precedent). Evidence cost of the 24 Sep
misalignment: dead 05:20-12:10 IST; within trading hours the open
through 12:10 was lost (~2.9 of the day's 6.25 trading hours).
Recovery was clean at 12:11:06 IST (breakers CLOSED, 06:41:06 UTC),
cycles executing real analysis by 12:12 IST. Supervisor unharmed
throughout (cycles 21k+, zero exceptions); OpenAlgo process death #3
(12:25 IST, silent, no WER) remains part of the SQLite-contention
wave request above.

Erratum note (24 Sep, principal pass): the first draft pinned a single
death at "06:35 IST (403)" with a "~2.5 trading hours" cost; a
LOATS-side log pass then re-pinned 05:20:17; the cross-layer
reconciliation against the OpenAlgo auth-layer log shows both are
STAGES of one progressive invalidation — 06:35 is the quotes-auth
stage, 05:20 the permission-stage onset. This section records the
reconciled sequence. Log line anchors: `logs/loats.log.5` line 52740
(onset), line 52747 (breaker OPEN); `logs/loats.log` line 944 (CLOSED
after recovery) — timestamps are the durable anchors, rotation will
retire the line numbers.
