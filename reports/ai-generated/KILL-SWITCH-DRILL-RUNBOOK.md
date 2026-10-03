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
   module-level singleton — the same flag every gate in the orchestrator,
   scheduler, and OpenAlgo adapter reads);
2. fetches the broker order book through OpenAlgo and cancels every
   OPEN/PENDING order it finds (in the current ANALYZE posture there are
   none — the safety loop runs and finds zero);
3. sends you a `🚨 KILL SWITCH ACTIVATED` alert.

While the flag is up, every trading cycle raises `KillSwitchError` at the
gate; the orchestrator logs `Kill switch active - trading cycle paused` and
idles on a 1-second poll. Nothing schedules, nothing orders. `/resume`
clears the flag and normal operation returns.

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

Expected: a status card ending with `🟢 ACTIVE`.

| If you see | It means | Do this |
|---|---|---|
| Status card, `🟢 ACTIVE` | Channel + process healthy | Continue to Step 2 |
| `Unauthorized: You are not authorized...` | Your user ID is not in `TELEGRAM_ADMIN_IDS` | Stop; ask the assistant to fix the config, retry another day |
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
| `Unauthorized...` | Same as Step 1 | See Step 1 |
| `Failed to activate kill switch.` | The order-book fetch failed, so the flag rolled itself back (safe failure) | Note the time; ask the assistant to check `logs/loats.log`; retry once after 5 minutes |
| `❌ Error: ...` | An exception inside the handler; flag rolled back | Copy the exact text and report it; do not retry until explained |

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

Send `/status` one last time. Expected: `🟢 ACTIVE`.

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
minutes apart, both inside the live span window. Paste those lines back to
the assistant (they contain no secrets) so the exercise is filed against
the span record before the 16 Oct close.

## Troubleshooting summary

| Symptom | Meaning | Action |
|---|---|---|
| Bot silent | Polling down / chat not STARTed | Assistant checks span + bot task |
| `Unauthorized...` | Admin allow-list mismatch | Assistant fixes `TELEGRAM_ADMIN_IDS` |
| `Failed to activate...` | Order-book fetch failed; flag rolled back (safe) | Wait 5 min, retry once, then investigate |
| `Failed to deactivate...` | Alert dispatch failed after release | Harmless; verify `/status`, report |
| Card stays `🟢` after `/kill` | Halt did not stick | Stop; assistant reads logs before anything else |
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
