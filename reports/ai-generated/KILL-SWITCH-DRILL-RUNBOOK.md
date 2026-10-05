# Kill-Switch Drill Runbook — Operator In-Span Exercise (P5)

Audience: the LOATS operator, driving the Telegram emergency halt for the
first time. No trading-system background assumed; every step lists what you
should see and what each alternative outcome means.

Why this drill exists: the CMP P5 gate requires a REAL operator-initiated
kill-switch exercise INSIDE the live supervised span, before that span
closes. The supervisor's own `kill_switch_verified` probe (one event per
writer generation) is state verification at generation start — it does NOT
satisfy the in-span exercise requirement. This drill, performed from your
own Telegram client, is the exercise the register tracks.

Deadline: **16 Oct 2026 20:08:05 UTC = 17 Oct 2026 01:38:05 IST** — the live
span `p5_forward_test_20261002_200805` closes at that instant (started
02 Oct 20:08:05Z; 14-day accumulation clock per R-16). Run the drill any
day before that, ideally during regular market hours (09:15–15:30 IST) so
the trading cycle is actively polling while you exercise the halt.

---

## What the kill switch actually does (30-second version)

Sent from your Telegram client, the `/kill` command:

1. flips an in-memory halt flag in the running LOATS process (`alerts.py`,
   module-level singleton — the same flag the trading-cycle gate and the
   OpenAlgo order-placement gates read);
2. fetches the broker order book through OpenAlgo and cancels every
   OPEN/PENDING order it finds (in the current ANALYZE posture there are
   none — the safety loop runs and finds zero);
3. sends you a `🚨 KILL SWITCH ACTIVATED` alert.

While the flag is up, every trading cycle raises `KillSwitchError` at the
gate; the orchestrator logs `Kill switch active - trading cycle paused` and
idles on a 1-second poll. No trading cycle runs and no order is placed.
Background support jobs (market-status refresh, data cleanup) keep running
— they place no orders. `/resume` clears the flag and normal operation
returns.

The flag lives in the running process: if the LOATS process restarts while
engaged, it comes back disengaged (and the supervisor re-verifies the halt
primitive at every generation start). That is why you stay at the wheel
between `/kill` and `/resume` — the whole engaged phase should last two to
five minutes, not hours.

## Before you start (2-minute preflight)

- Your bot chat exists and you pressed START on it once (a bot cannot
  message you until you do).
- Your Telegram user ID is in `TELEGRAM_ADMIN_IDS` (on file: `694928527`).
  The bot rejects `/kill` and `/resume` from anyone else — by design.
- The LOATS process with the alert bot is running. Practical liveness
  proof: the bot answers `/status` (Step 1). Deep health check (snapshot
  mtime + counter quartet) is the assistant's job, not yours.

## The drill (10 minutes)

### Step 1 — Prove the command channel: send `/status`

Send exactly:

```
/status
```

Expected: a status card whose Status line reads `🟢 ACTIVE` (the card
continues with a `Source breakers` block after that line — that is
normal). `/status` is read-only and open to any chat member; the admin
allow-list gates `/kill` and `/resume`, which you exercise at Steps 2
and 4.

| If you see | It means | Do this |
|---|---|---|
| Status card, Status line `🟢 ACTIVE` | Channel + process healthy | Continue to Step 2 |
| Nothing at all (60+ s) | Bot polling down, or chat never STARTed | Stop; ask the assistant to check the span and the bot polling task |
| An error mentioning Telegram | Transient network/API fault | Wait 2 minutes, resend once; if it repeats, stop and report |

### Step 2 — Engage the halt: send `/kill` with a reason

Send exactly (the words after `/kill` become the recorded reason — keep the
drill label so the log line is self-describing):

```
/kill In-span drill activation before 16Oct close
```

Expected, in this order:

1. your reason echoed inside a `🚨 KILL SWITCH ACTIVATED` alert
   (timestamp shown in UTC);
2. the bot's reply: `🚨 Kill switch activated successfully.`

| If you see | It means | Do this |
|---|---|---|
| Both messages above | Halt engaged, orders loop ran clean | Go to Step 3 within a few minutes |
| `⚠️ Kill switch already active.` | The halt was ALREADY engaged | Do NOT proceed blindly; ask the assistant to read the logs first, then decide |
| `Unauthorized...` | Your user ID is not in `TELEGRAM_ADMIN_IDS` | Stop; ask the assistant to fix the config, retry another day |
| `Failed to activate kill switch.` | AMBIGUOUS — either the order-book fetch failed and the flag rolled back (safe), OR the alert channel's 5-minute cooldown suppressed the confirmation while the halt IS engaged | **Send `/status` immediately.** Status line `🔴 KILL SWITCH ACTIVE` = the halt IS engaged: continue to Step 3 and finish the drill normally. Status line `🟢 ACTIVE` = the flag really rolled back: wait at least 6 minutes (cooldown margin), then retry Step 2 once |
| `❌ Error: ...` | An exception inside the handler; flag rolled back | Copy the exact text and report it; do not retry until explained |

> **Never paste shell or log text into the chat.** Type `/kill`, `/resume`,
> and `/status` as bare commands only. Until the 05-Oct fix the bot also
> matched *free text*: any message merely containing the word "kill" (or
> "resume"/"start") engaged or released the halt — on 05 Oct a pasted
> log-verification line mentioning "Kill switch" was executed as a real
> activation. A command with a trailing paste can still mis-fire if the
> paste rides along in the same message.

### Step 3 — Observe the engaged state (stay here 1–2 minutes)

Send `/status` again.

Expected: the same card, now ending `🔴 KILL SWITCH ACTIVE`.

In `logs/loats.log` the cycle loop now logs `Kill switch active - trading
cycle paused` once per cycle (JSON lines, UTC `Z` timestamps).

If the card still shows `🟢 ACTIVE`, the halt did not stick — treat as a
Step-2 failure mode and report; do not continue.

### Step 4 — Release the halt: send `/resume`

Send exactly:

```
/resume In-span drill deactivation
```

Expected:

1. a `✅ KILL SWITCH DEACTIVATED` alert;
2. the bot's reply: `✅ Kill switch deactivated successfully.`

| If you see | It means | Do this |
|---|---|---|
| Both messages above | Halt released, normal operation resumes | Go to Step 5 |
| `ℹ️ Kill switch not active.` | The halt was not engaged anymore — usually the process restarted between Steps 2 and 4 | Re-run the drill from Step 2; report the restart to the assistant |
| `Failed to deactivate kill switch.` | Rare: the flag cleared but the confirmation alert could not be sent | The system IS resumed — verify with `/status`, then report the alert failure |

### Step 5 — Confirm restoration

Send `/status` one last time. Expected: Status line `🟢 ACTIVE`.

### Step 6 — Evidence capture (PowerShell 5.1)

The graded evidence is the log lines. `logs/loats.log` is JSON-lines with
UTC `Z` timestamps (IST = UTC + 5:30); rotation may push early entries into
`loats.log.1` and older — the wildcard below covers those. From any
PowerShell window:

```powershell
Select-String -Path "G:\.OA\LOATS-13July2026\LOATS13July2026\logs\loats.log*" -Pattern "Kill switch activated","Kill switch deactivated" | Select-Object -Last 8
```

Expect the activation pair (`Kill switch activated: In-span drill
activation before 16Oct close`) and the deactivation line, timestamps a few
minutes apart, both inside the live span window. You will also see extra
matched lines (`Alert sent: [error] 🚨 <b>KILL SWITCH ACTIVATED</b>...` and
their JSON error copies) — those are the alert-dispatch confirmations of
the same events, not anomalies. Paste what you get back to the assistant
(the lines contain no secrets) so the exercise is filed against the span
record before the 16 Oct close.

## 05 Oct 2026 in-span exercise — filed record

P1 kill-switch drill executed in-span on 05 Oct 2026:

- **Activation** `Kill switch activated: In-span drill activation before
  16Oct close` at `2026-10-05T05:57:18Z`, confirmation alert 05:57:18Z.
- **Enforcement** the cycle loop logged `Kill switch active - trading
  cycle paused` pairs through the whole window until release (JSON lines,
  1 Hz).
- **Deactivation** `Kill switch deactivated: In-span drill deactivation`
  at `2026-10-05T06:00:54Z`, confirmation alert 06:00:56Z. The graded leg
  passed; `kill_switch_verified: true` on the live span snapshot.

Free-text misroute recurrence (documented, pre-#134 host): after the
graded leg, a pasted log-verification line mentioning "Kill switch"
engaged the halt twice more — `2026-10-05T06:01:59Z` and
`2026-10-05T09:24:21Z`. The routing fix (commit `8dc850b`, PR #134,
merged 07:06:19Z) was on `main` but the host process predated it; the fix
loads only on restart. Until then: bare `/kill`, `/resume`, `/status`
only, never a paste riding after a command. The kill flag is in-memory
(`src/loats/alerts.py`), so the pending restart — or a bare `/resume` —
clears the 09:24:21Z activation.

Amended 05Oct2026 (evening, post-drill restart): the restart LANDED —
the pre-#136 supervisor generation was soft-stopped at 18:45 IST
(span `p5_forward_test_20261002_200805.json` closed gracefully,
`unhandled_exceptions: 0`) and the watchdog fresh-started
`p5_forward_test_20261005_131805.json` at 13:18:05Z (18:48 IST) on the
merged code (recorded `kill_switch_active_at_start: false` — the stuck
09:24:21Z activation cleared with the process). The command-only
routing and the R-19 scheduler-halt gate are live in this generation.
The paragraph above stands as the until-restart record; the bare-command
discipline remains the standing rule.

Engaged-state truth (R-19): support jobs (market-status refresh, session
activation, data cleanup, backtest sanity) kept running during the
05Oct halt — true for THAT generation, which predated the gate; the
scheduler-scope wiring (gate every job entry on `_check_kill_switch`)
landed in `fix/r19-scheduler-halt-gate-05oct` and is effective from the
same 05Oct restart, so a future engaged halt now refuses every scheduled
job body.

## Troubleshooting summary

| Symptom | Meaning | Action |
|---|---|---|
| Bot silent | Polling down / chat not STARTed | Assistant checks span + bot task |
| `Unauthorized...` (Steps 2/4) | Admin allow-list mismatch | Assistant fixes `TELEGRAM_ADMIN_IDS` |
| `Failed to activate...` | AMBIGUOUS (rollback OR cooldown suppression with halt engaged) | `/status` immediately: 🔴 = engaged, continue Step 3; 🟢 = rolled back, wait 6 min, retry once |
| Halt engaged with no `/kill` sent | Free text containing "kill" was pasted as a message (pre-05-Oct-fix routing) | Send `/resume` as a bare command, verify with `/status` |
| `Failed to deactivate...` | Alert dispatch failed after release | Harmless; verify `/status`, report |
| Card Status line stays `🟢` after `/kill` | Halt did not stick | Stop; assistant reads logs before anything else |
| Process restart mid-drill | In-memory flag reset to disengaged | Re-run from Step 2; report the restart |

## After the drill

- Leave the span alone — no restarts, no config edits — so the exercise
  lands inside an unbroken generation.
- The register keeps R-12's reconciliation clock: the graded span must also
  carry-or-fire routed attempts before `ended_at`, else it grades
  FAIL-closed by design (that part is the system's job, not yours).
- If anything in the drill misbehaved, the paste-back of Steps 1–6 outputs
  plus the `Select-String` lines is everything the assistant needs to
  root-cause it — nothing else to capture.

Reference: `docs/RISK-REGISTER.md` (R-12 row and the 2026-10-03 updated
entries), `docs/adr/0018-p5-preguard-killswitch-disclosure.md`,
`docs/adr/0020-killswitch-escalation-analyze-acceptance.md`,
`src/loats/alerts.py` (handlers `_kill_switch` / `_resume`).
