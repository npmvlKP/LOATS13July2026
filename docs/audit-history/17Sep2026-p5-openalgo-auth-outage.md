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
   the same-day in-session breaker storms as annotation-only outage
   windows, mirroring the 17Sep precedent: 21Sep (10:08–10:37 and
   12:14–12:27 IST clusters), 23Sep (~09:42–09:45 cluster), 24Sep
   (09:15–12:09 IST session-stale storm — token-expiry wall,
   Continuation 3; self-recovered 12:11:06 IST), and 25Sep
   (09:15–14:29 IST storm — Continuation 4; recovered by operator
   re-auth 14:29:05 IST).

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

## Continuation 4 (25 Sep): second consecutive pre-band login — full morning lost

**Recurrence confirmed the mechanism and quantified the cost.** The
automation's morning cycle logged in at 04:48:12 IST (row 107, oauth
zerodha) — again inside the 05:20+ invalidation band. Progressive
sequence identical: 05:29:59 history-permission denials, 06:15+ steady
~2/min `Incorrect api_key or access_token` (413 by 09:17), 07:06
websocket goodbye + 403 handshake. Session stale from the band through
14:29 IST — no operator re-login across the entire morning. In-session
storm: 1,515 opens. **Recovery**: operator re-auth 14:28:35/14:29:05
IST (rows 108/109); last breaker open 14:29:06; afternoon banked 289
provenance-locked decisions in 61 minutes (~4.8/min, span-best rate).
Day cost: ~5.25 of 6.25 trading hours.

**Pattern data for the wave owner**: two consecutive days (24–25Sep),
identical root cause (login scheduled inside the invalidation band),
identical signature, combined ~10 trading hours of evidence loss on
the two highest-leverage sessions then remaining. The single
high-leverage fix remains moving the automation's daily login step to
**after 08:00 IST**. On 28Sep the operator self-served at 06:44:04 IST
and the band did not fire — evidence the band is not deterministic;
the post-band-login rule stands as the only reliable play.

## Continuation 5 (28 Sep): new failure class — silent staleness (transport green, data dead)

**Signature**: the sentiment source served content up to 279 minutes
old through the 28Sep session while its transport stayed perfectly
healthy — 6,777/6,777 successful fetches, circuit `closed`, zero
errors. The only signal was the orchestrator's content-age warning
("liveness ALERT ... exceeds the 15.0 min freshness threshold during
REGULAR session"), 1,064 warnings from ~08:30 IST, staleness climbing
monotonically 15 → 279 min; onset just after the open (last-fresh
≈ 08:15 IST), no recovery by 13:30 IST.

**Downstream effect**: zero audit rows of ANY kind on the day — the
freshness gate kills candidate formation upstream of the rejecting
stage (prudence days still write REJECT rows; this day writes
nothing). Routing verified enabled (fresh engine identity 06:13 IST,
enabled-at-start true, zero disabled-routes); all other sources
healthy; broker session valid (operator 06:44:04 login).

**Corrections at day close (16:10 IST digest reconciliation)**: (1) the
5 in-session breaker opens today were NOT stale-window chatter — they
are 12:14:26–12:14:33 IST (log stamps 06:44Z are UTC; an earlier draft
of this section misread them as IST), a 63-second openalgo storm
self-recovered by 12:15:28 — the 7th recurrence of the **pinned R-13
class** (untimed newspaper4k downloads starving the producer window),
whose remediation rides the 30Sep wave; the watch bucketed it
correctly. (2) The digest attributes the floored counters to the
known **R-14 producer starvation** (producer cancelled each cycle
before persisting; fix also riding 30Sep) rather than to the sentiment
staleness alone. Both mechanisms are real in today's logs (1,064
staleness warnings AND zero persisted rows); whether staleness is the
trigger for the cancels or an independent co-cause will be
discriminated by the 30Sep fix landing — if rows flow Tuesday, R-14
was the binding constraint and this section's gate explanation is
downstream detail.

**Outcome (29 Sep close): rows flowed — R-14 cleared.** 270 REJECT
rows written today (`signal_batch` entities, composite_strength ~0.56
declines — the prudence class, not starvation), sentiment recovered
(15 marginal liveness alerts, max 17 min stale vs 279 the day before),
zero ROUTE rows all session. The 29Sep close digest's "26–29Sep all
zero" phrasing is true only for ROUTE rows; the REJECT stream is the
recovery evidence. Day classification: **prudence day on fully
restored machinery** — candidate formation works, the gate binds on
signal strength (0.56 vs threshold), exactly the 23Sep-class regime.
One consequence for grading: the zero-ROUTE streak (26, 28, 29 Sep)
is a signal-strength drought on live machinery, distinct from the
24–25Sep session-outage days — density-quality grading should weigh
them differently.

**Operator-adopted annotation (29Sep evening, keep+annotate verdict;
live probes by the remediation session)**: the Outcome paragraph above
is kept verbatim with two claim-level corrections pinned here, per the
live evidence of the same day. (1) "R-14 cleared" is FALSIFIED — the
deferred-cancellation signature ran all day: 23,945 producer
budget-warning events with per-minute maxima up to 41.6 s (over the
8.0 s window, 428 of 457 active minutes), sentiment staleness
reaching 95+ min during REGULAR (49 `Sentiment source liveness ALERT`
log warnings — none delivered, the F9-H-03 alert was log-only), and
zero sentiment persists into the evening. The 270 REJECT count, the
prudence-day classification, and the "zero-ROUTE = strength drought"
distinction are CONFIRMED against `data/loats.db` (`audit_log`:
270 `signal_batch`/REJECT rows 29Sep; `trade_decisions`: last row
25Sep 09:59Z). (2) "15 marginal liveness alerts, max 17 min stale" is
FALSIFIED on both counts (49 alerts; 95-min peak). Fix disposition:
shape (i)+(iv) from the R-14 register row landed 29Sep evening
(bounded download leg: socket timeout + wait bound + concurrency cap +
per-feed fetch timeout + per-feed sweep budget with partial retention;
failure negative-cache; liveness escalation now delivers to Telegram
with once-per-episode dedupe and recovery re-arm; polling-task
dead-man switch for the silent-bot class). Verification suite:
`tests/test_r14_bounds_and_liveness_alert.py`.

**Operator-adopted annotation (28Sep, keep+annotate verdict; live
probes at HEAD `d0bfaf0`)**: the corrections block is kept with three
claim-level fixes pinned here. (1) The 12:14 IST storm IS the SIXTH
occurrence the register already pins (`28Sep2026-r13-sixth-occurrence.md`)
— not a seventh; no count increment. (2) The untimed newspaper4k
download mechanism belongs to **R-14** (sentiment producer starvation,
P2-watch, rides the 30Sep window), not R-13 — R-13 is the
breaker-storm class; the corrections text conflated the two register
rows. (3) The "63-second storm" span is the GLOBAL breaker only
(openalgo 06:44:26Z open → 06:45:28Z close = 62 s); the four
per-source breakers stayed open until 06:46:32Z (full storm 2m06s),
so the fail-closed refusal window is the register's ~2 min. Kept as
corroborated live: the R-14 starvation attribution, zero persisted
sentiment rows on the day against 2,077 freshness events (liveness
ALERTs reaching 445 min staleness), and the 30Sep remediation ride.

**Why this class is distinct**: breaker architecture correctly keeps
the circuit closed (transport is fine); a successful fetch of dead
content is invisible to every existing alarm except the 15-min
warning. Wave items suggested: (a) escalate sustained stale-content
beyond a threshold (e.g. 60 min in-session) to a degraded state that
surfaces in run health, not just log warnings; (b) operator runbook:
"liveness ALERT on a zero-error source = check upstream feed
reachability (RSS), not the transport." Suspected trigger today:
upstream RSS reachability from this host — broker-path transport
unaffected, consistent with feed-side outage or egress filtering.

## Continuation 6 (01 Oct): pre-band trap fires again; band fingerprint extended

**Recurrence #3 of the pre-band login trap** (24Sep, 25Sep, 01Oct):
automation oauth at 04:55:26 IST (row 133) — inside the band. The
progressive sequence ran with **earlier hard-failure onset than
previously documented**: precursor `Server disconnected` transients at
04:57:51 and 05:26:13, a clean gap to 06:32, then hard `Incorrect
api_key` quotes rejections from **06:33 IST steady at 2/min** (vs the
06:19–07:49 quotes-stage range previously pinned). WS goodbye + 403 at
07:05:39. No operator re-login as of 09:16 IST; open bell will fail
hard without one. 91.5k breaker events burned by 09:10; all four
broker-backed circuits OPEN, fail-closed (no order routing).

**Extended fingerprint for the record**: the band's hard-rejection
onset is variable (observed 06:19, 06:33, 06:35, 06:38 across days);
its precursors (`Server disconnected` transients in the 04:57–05:26
window) are now logged as early warning signs — a `Server disconnected`
after a fresh pre-dawn oauth should trigger an immediate re-login
attempt rather than a wait for hard failures.

**Day classification pending re-auth**: if recovered pre-open or
early, a partial evidence day; if absent-operator (25Sep pattern), a
full loss. Gate mark for this run is 2026-10-13 19:48:04 IST (run
141804's clock) — the reminder's "2026-10-08" reference was stale
context from the superseded 080208 clock.

**Operator annotation (01 Oct 2026, live probe verification at
09:33–09:50 IST, LOATS rotations `logs/loats.log[.1-.3]`) — the
transcript claims verify against instrumented evidence, with the
source layer named per the pinned attribution set**: (1) the oauth
04:55:26 IST row and the WS goodbye + 403 at 07:05:39 IST are
OpenAlgo HOST-layer emitters (host `logs/` holds no 01 Oct rotation;
not corroborable from LOATS-side instrumentation — transcript-sourced,
consistent with the 30Sep collapse-#17 precedent); (2) the `Server
disconnected` precursors are CORROBORATED at 23:27:52Z and 23:56:14Z
(01 Oct 04:57:52 / 05:26:14 IST — the transcript's second-level
04:57:51 / 05:26:13 stamps differ by ≤2 s, receipt-time skew;
LOATS `loats.openalgo` HTTP-500 events, `.3`); (3) the hard
`Incorrect api_key` quotes rejections are
CORROBORATED: onset 01:03:09Z = 06:33:09 IST, steady exactly 2/min
for every minute 01:03–01:53Z (`.2`), then silenced by the global
`openalgo` breaker OPEN (fetch attempts suppressed — rejection
silence is a breaker effect, not recovery); (4) the 91.5k breaker
claim is CORROBORATED at order of magnitude: 99,642 breaker/degraded
events 23:00Z–03:45Z across `.3/.2/.1` + live, same growth class as
the 25Sep storm (~14.8k) at higher cycle cadence; (5) all four
broker-backed circuits OPEN and fail-closed, zero `auth success` /
re-login rows in the LOATS stream through 04:20Z — the day
classifies FULL LOSS (25Sep pattern) unless the operator recovers
late; the 13 Oct 19:48:04 IST gate mark on run 141804's clock is
correct (29Sep 14:18:04Z + 14d).

**Closing addendum (01 Oct, recovery verified 13:37 IST — LOATS-side,
first-hand probes).** The operator re-auth landed 13:19:52 IST (host
brlogin success; fresh master contract 106,187 symbols loaded
13:20:22 IST). The global `openalgo` breaker CLOSED after recovery at
07:50:21Z (13:20:21 IST — 29 s after re-auth, the designed
HALF_OPEN→CLOSED arc) and all four source breakers by 07:50:52Z.
Day classification per the pending clause above: **PARTIAL EVIDENCE
DAY** — recovered mid-session (13:19:52 IST), producers starved from
the 04:57 IST precursor through 13:20:52 IST (hard rejections
06:33–07:23 IST, then suppression by the OPEN global breaker —
rejection silence was a breaker effect, not recovery), evidence
resumes from 13:20:52 IST. This is NOT the 25Sep absent-operator
pattern: the operator re-authed, late. Two same-window control
results: the 13:14 IST `/kill` attempt correctly REFUSED activation
(`Failed fetch orders kill switch, rolled back` — the kill switch
must reach the broker to cancel orders; fail-closed rollback proven),
and the 13:33 IST re-drill PASSED on all legs (activation 08:03:04Z,
122 orchestrator-blocked cycles, deactivation 08:05:12Z,
`kill_switch_verified: true`) — the kill-switch live exercise
landed inside the span despite the outage. The verifier's
`DOCUMENTED_OUTAGE_WINDOWS` entry for this recurrence is now bounded
(23:27:52Z → 02:50:21Z); grading against the bounded window is the
grader's contract, not this addendum's.

**Erratum (28Sep session, ~14:06 IST live probes — root cause
corrected).** Continuation 4's anchors re-verified against live state
and stand: 289 `trade_decisions` rows for 2026-09-25 (DB) = 289
`Routing TradeDecision` log lines; recovery cluster 08:58–08:59Z.
Continuation 5's observations stand (zero audit rows, routing quartet,
breaker green, monotonic staleness); its MECHANISM and TRIGGER do not
survive probing:

- Feed reachability is NOT the cause. All three configured feeds
  fetched from this host in <0.5s at 14:00 IST (economictimes 50
  entries, moneycontrol 15, livemint 35; newest entries same-hour);
  zero `Failed parse RSS feed` / `Failed process RSS item` events all
  day. No dead content was ever served — rows simply stopped
  persisting.
- Gate-age semantics: the 15-min gate measures time since the last
  PERSISTED sentiment signal
  (`async_get_latest_signals(scan_type='sentiment')` filters on
  `signals.metadata.scan_type`), not article age. Last persist
  02:28:22Z = 07:58:22 IST (349 rows that day, all |score| 0.76–0.80
  vs the 0.05 threshold, news_count 55, degraded=0 — healthy computes
  right up to the stop). First alert 09:15:31 IST (77 min), not
  ~08:30; staleness still climbing past 368 min at 14:06 IST with
  1,587 alerts and zero recovery — the day's sentiment leg is lost.
- Root cause: untimed article downloads. `parse_rss_feed` extracts up
  to ~60 article pages per sweep via newspaper4k (`Article.download()`,
  no timeout) sequentially inside the 8.0s producer window. Live
  measurement from this host: 4.3–5.7s per economictimes article,
  16.6–26.6s moneycontrol, 5.9–19.3s livemint. Morning cycles survived
  on the per-URL download cache (TTL 5 min, same-article hits); once
  cold-article churn pushed sweep cost past the window (07:58 IST),
  the producer window cancelled the sweep EVERY cycle — the budget
  warnings' median pinned at 8,003–8,009ms from 03Z onward is the 8.0s
  window firing to the millisecond. Cancelled cycles seed no caches,
  so every cycle re-pays cold downloads: self-sustaining through the
  close. Transport counters stay green because feedparser GETs succeed
  instantly and the breaker counts only raised exceptions (8,009/8,009
  successful, zero failed — P5 snapshot 13:56 IST).
- Corrected wave items: (a) stands — escalate sustained gate
  starvation to run health; (b) inverted — "liveness ALERT on a
  zero-error source = check ARTICLE-DOWNLOAD latency (the newspaper
  leg), not feed reachability"; (c) new — bound the download leg
  (per-download timeout plus a concurrency cap, or defer cold
  downloads to the existing detached cache-only refresh) and/or
  persist a liveness row per completed analysis independent of
  downstream signal gating. Pinned as R-14 in the risk register; the
  decision rides the 30Sep window under the ADR-0016 freeze.

## Continuation 7 (06 Oct): NEW failure class — Kite Connect APP-KEY rejection (subscription lapse)

**Distinct from every prior class**: Zerodha rejects OpenAlgo's
configured `BROKER_API_KEY` at the OAuth ENTRY POINT —
`kite.zerodha.com/connect/login?api_key=…` renders
`{"status":"error","message":"Invalid api_key.","error_type":"InputException"}`
byte-identical twice. The same key produced a successful oauth at
05Oct 08:39:59 IST, so this is an **app-level revocation or Kite
Connect subscription lapse**, not the daily token band (whose
rejections come from the quotes API after a formerly-valid login).

**Consequence**: NO OAuth is possible for anyone — the Kite login page
never loads, so password/TOTP are unreachable and neither the operator
nor any agent flow can refresh the session until the app is renewed or
a new key+secret is issued at developers.kite.trade and installed in
`G:/.OA/OpenAlgo/.env` (`BROKER_API_KEY`/`BROKER_API_SECRET`; current
`*_MARKET` fields are still placeholders). Automated re-login job
verified the block 08:35–08:47 IST and correctly escalated.

**Impact**: LOATS breaker storm 305 opens with zero recoveries (last
07:43 IST UTC stamps) [FALSIFIED at the 06Oct reconciliation: the live
rotations carry 79,023 breaker-open log lines (degraded-fetch +
open-state) and 3,389 OPENED/HALF_OPEN state transitions for the day —
14 global `openalgo` OPENED events cycling against 338 HALF_OPEN
recovery probes, last OPENED transition 07:30:19.606Z = 13:00:19 IST]; run
200805 decisional counters frozen at 74 (Monday's burst) [run 200805
closed gracefully 2026-10-05T13:15:22Z — the LIVE span at writing was
`p5_forward_test_20261005_145804.json`, whose decisional counters read
0 through the outage and 2 after recovery (both DB-corroborated in
`trade_decisions`)] — evidence accrual halted for the day unless the key
is fixed intraday. Day cost at 09:30 IST: full open lost. This is the
fourth credential-adjacent outage class of the span (band expiry,
pre-band login, host-reboot token loss, now app-key rejection) and the
first that is **not self-healing by any local action**.

**Remediation (operator-only, credentials out of bounds by policy)**:
developers.kite.trade → app `r6ybr72h46z9uxqh` subscription status →
renew or rotate → update `.env` → restart OpenAlgo → OpenAlgo UI
re-login (password + TOTP) → LOATS breakers close within ~90 s
(standard recovery). The pending P1 in-span kill drill remains owed
after session restoration (before 19 Oct 20:28 IST).


## Continuation 7 closure (06 Oct, recovery verified ~13:20 IST —
LOATS-side, first-hand probes)

The operator remediation landed: OpenAlgo broker callback success
13:00:29 IST, session login time stamped 13:00:29.882+05:30; master
contract refreshed (108,566 symbols loaded by 13:01:13 IST). The global
`openalgo` breaker CLOSED after recovery at `2026-10-06T07:31:19Z`
(13:01:19 IST — 50 s after re-auth, the designed HALF_OPEN→CLOSED arc)
with all four source breakers CLOSED by 07:32:05.55Z (13:02:05 IST).
Zero breaker OPENED transitions after 07:30:19.606Z (day total 3,389
OPENED/HALF_OPEN transitions; window bounded below). Verified
consequences on the live 145804 span: zero
M-01 cycle-failure budget escalations after 07:07:35.64Z (day total
28, every activation refused fail-closed by the open breaker — the
documented refuse-and-rearm degradation loop, never a real halt; zero
in-memory kill-switch halts engaged all day), decisional leg resumed
07:37:07Z — decisions `decision_20261006073706863317_66763040` and
`decision_20261006073714830930_11043b59` routed and persisted
(`trade_decisions`, `as_of_date` 2026-10-06, counters 0 → 2), and the
sentiment leg resumed persisting from 07:31:57Z (1,268 rows 13:02 IST
onward; exactly 4 rows in the 05:15–07:32Z stall window — consistent
with the #140 session-gated-drain disposition). The P1 in-span kill
drill is NOT discharged by this recovery or by the refused
auto-escalations; it remains owed inside 09:15–15:30 IST before
19 Oct 20:28 IST.


**Outcome (06Oct close, 07Oct digest corroboration)**: operator
renewed the subscription and re-logged — oauth 13:00:29 IST (row 162),
openalgo CLOSED 13:01:19, all sources by 13:02:05 (registry pin
PR #149: CLOSE 08:09:29.7Z / 08:10:01–11Z); zero breaker transitions
after; 63/63 rows==counters banked in the recovered window. Day cost:
~3h46m in-session (~60%). The registry pin for this window is PAID
(PR #149), unlike the 21/23–25Sep pins still pending with the F9-C-02
owner.

## Continuation 8 (07 Oct): fifth credential-adjacent outage - pre-band
login trap, transport-then-token shape (recovery verified 13:40 IST -
LOATS-side, first-hand probes)

Classified at the broker's OAuth ENTRY POINT: the operator's host re-auth
succeeded on the FIRST attempt (brlogin callback success
2026-10-07T08:09:03Z = 13:39:03 IST; session login stamped 13:39:03 IST;
app key healthy throughout - no app-level `Invalid api_key` at OAuth,
unlike 06Oct). This is therefore the daily-band/stale-session class
(24Sep, 01Oct, 07Oct fingerprint), and it arrived in a NEW two-phase
shape: transport-dead first, token-wall second.

### Phases (all stamps UTC; IST = +5:30)

- Phase 1 - transport-dead: first LOATS-observed failure
  2026-10-06T23:40:20Z (05:10:20 IST 07Oct; global `openalgo` breaker
  OPENED after 30 consecutive failures; `All connection attempts
  failed`). The rotation boundary falls at 23:40:15Z, so onset is
  bounded to [23:40:15Z, 23:40:20Z]; the previous rotation ends
  mid-storm with no retained evidence of earlier trouble. 58
  transport-class lines retained, 56 of them in the 00Z hour.
- Phase 2 - token-wall: first hard `Incorrect api_key or access_token`
  rejection 2026-10-07T00:09:01Z (05:39:01 IST), steady ~2/min for
  ~8h15m (921 token-class lines; hourly bands 116-127/h). The 06:00:10
  IST automation oauth fired INSIDE the storm and did not heal it
  (broker-side invalidation is progressive; the new token died like its
  predecessor).
- Remission: exactly one breaker CLOSE/recovery arc
  00:30:48Z-00:41:07Z (06:00:48-06:11:07 IST) straddling that oauth;
  the global breaker re-OPENED at 00:41:07Z and the token wall resumed -
  one continuous failure state, not two episodes.
- Recovery: operator re-auth 08:09:03Z (13:39:03 IST, ONE attempt - no
  lockout burn this cycle); master contract refreshed (108,383 symbols;
  cache loaded in 3.67 s); `openalgo` transitioning to HALF_OPEN
  08:09:27Z, CLOSED after recovery 08:09:29Z (13:39:29 IST); all four
  source breakers CLOSED by 08:10:11.656Z (13:40:11 IST).

### Storm totals (07Oct LOATS rotations; window 23:40:20Z-08:09:29Z)

- Breaker transitions: 2,425 OPENED across the five breakers inside the
  window; day totals 466 OPENED per breaker (466 OPENED + 467
  HALF_OPEN-transition lines each) - far denser than the 06Oct app-key
  day (3,389 transitions of which this window alone carries 2,425).
- Escalation/kill loop: 51 `Kill switch activated` lines in-window,
  EVERY one the attempted-then-rolled-back signature: 50 M-01
  cycle-failure budget escalations (first 2026-10-06T23:49:15.515Z =
  05:19:15 IST, nine minutes after onset - the 500-consecutive budget
  re-arms after each half-open probe, so escalations repeat through the
  storm; last 2026-10-07T08:07:59.115Z) + 1 operator drill attempt
  (`In-span drill activation before 16Oct close`, 08:01:20Z =
  13:31:20 IST, refused by the open breaker 54.2 s). Zero engagements:
  `kill_switch_active_at_start` false on the live span; zero
  kill/auth-class lines after 08:09:03Z.
- Sentiment leg: exactly 4 rows inside the storm window
  (00:04:07Z-08:01:52Z), consistent with the #140 session-gated-drain
  posture; write-through resumed 08:09:53Z (1,596 further rows by day
  end; day total 2,864).
- Decisional leg: ZERO routing log lines and ZERO `trade_decisions`
  rows in-window - the cycle-failure budget (500 consecutive) exhausted
  long before the decisional leg could fire; the documented outage
  window therefore bounds a full decisional-evidence hole.
- Paste-vs-log note: the operator console showed red breakers at the
  13:30-13:35 IST /status probes and the 13:31 IST /kill refusal; the
  13:35 IST /resume correctly reported the switch not active (it never
  engaged). All consistent with the rotations above (last pre-recovery
  OPEN 08:08:28Z, drill refusal 08:01:20Z, M-01 escalation 08:07:59Z).

### Verified consequences on the live 20261005_145804 span (post-recovery)

Routing resumed 08:10:08Z (first post-recovery line; 136 routings by
08:30:17Z); `trade_decisions` accumulated 139 rows with `as_of_date`
2026-10-07 (created 08:10:08Z-08:30:50Z; in-span counters 0 -> 139);
the 08:29:38Z snapshot reads all five breakers closed (consecutive
successes 186-375 broker-backed, 2,260 sentiment; `last_failure` null)
with zero OPENED transitions after 08:10:11.656Z and zero
word-boundary auth-class lines after 08:09:03Z (a 08:24:10Z apparent
hit was a scan artifact - the substring `403` inside `3403.64ms`; the
recovery held). The P1 in-span kill drill is NOT discharged by this
recovery or by the 51 refused activations; it remains owed inside
09:15-15:30 IST before 19 Oct 20:28 IST. The storm-settled gate
condition for the operator-gated L-03 lot-size constant correction
(register entry 3) is now MET: the correction may proceed on the next
build wave.


## Continuation 9 (07 Oct): recovery-path forensics - vault TOTP desync; interactive recovery only

*Reconciled 07Oct ~16:5x IST: this section arrived as a foreign draft inserted ahead of the Continuation 7 closure under a duplicate Continuation 8 ordinal; it is retained here with chronology restored. Every probed figure verified against the LOATS rotations and store: 1,285 in-session breaker opens, 212 counted routings (span counter, 10:17Z probe), 63/275 trade_decisions rows (as_of 2026-10-06/07), breaker closes 13:39:29-13:40:11 IST.*

**Sequence**: operator oauth 06:00:10 IST landed mid-band and bought
only ~10 minutes before progressive re-invalidation (clean gap then
continuous 2/min auth errors from 06:11). The 08:35 automated
re-login then hit a NEW block: the Hermes vault's stored Kite TOTP
secret is **deterministically desynced** — 2 in-window `Invalid TOTP`
rejections (fresh-30s-window submission each time); the job stopped
at 2 to protect the account's 3 remaining lockout attempts. With the
vault path dead, NO oauth was possible until the operator logged in
interactively at 13:39:03 IST (rows 166/167) — probe HTTP 200,
breakers closed 13:39:29–13:40:11, zero events after.

**Day cost**: session dead 05:59→13:39 IST (~4h25m in-session, ~71%);
storm 1,285 in-session opens; recovered window banked 275 rows / 212
counted routings in ~80 min (~2.6/min). The 63-row vs 212-counter
delta at close is an emitter-vs-disposition scoping question (digest
§3) — probe scheduled next session, not a divergence (flag = 0).

**Two lessons banked**: (1) mid-band logins are worse than none — a
fresh token burned inside the band buys ~10 minutes then dies, and
the operator believes they logged in successfully; (2) the TOTP
desync means the credential chain now has THREE independent single
points of failure (app key subscription, daily token, vault TOTP
secret) — only the token self-heals locally. The post-market fix is
operator re-enrollment of Zerodha 2FA + vault item update; until
then, every band-trap morning requires interactive recovery.
