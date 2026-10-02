# Telegram Bot — Beginner's Guide for LOATS
(Create a bot, connect it to this project, revive the dead span)

This is the exact path for **this repo** (`LOATS13July2026`). The project
already has all the code: `src/loats/alerts.py` (class `AlertSystem`) reads
three settings from `.env` — `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
`TELEGRAM_ADMIN_IDS`. You only need to create the bot and feed it the
values.

---

## Part A — Create the bot on Telegram (5 minutes, all in the app)

1. Open Telegram (phone or desktop).
2. In the search bar type: `@BotFather` — the one with a **blue check**.
   Start a chat with it.
3. Send: `/newbot`
4. BotFather asks for a **display name**. Type anything human, e.g.:
   `LOATS Alerts Bot`
5. BotFather asks for a **username**. It must be unique and end in `bot`,
   e.g.: `opnalgokp_bot` (taken — pick your own variant).
6. BotFather replies with a **token**, a long string like:
   `1234567890:AAE4xxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
   - **Copy it. Store it safely. Never paste it in chats, screenshots,
     or any file that could be committed.** The token IS the bot's
     password. (If it ever leaks: send `/revoke` to BotFather — the old
     token dies instantly.)
7. Press **START** on your new bot's chat (or send `/start`). A bot can
   never message you until you do this once — this is Telegram's rule,
   not a bug.

## Part B — Find your numeric chat ID (2 minutes)

Chat IDs are **numbers**, not `@usernames`. Yours is `694928527`
(recorded 05Sep2026 for chat owner @KPPerumalla), but verify:

1. In PowerShell (the token in the URL is fine here — this is Telegram's
   own API, always use `curl.exe`, not PowerShell's `curl` alias):

   ```powershell
   curl.exe -s "https://api.telegram.org/bot<PASTE-TOKEN>/getUpdates"
   ```

2. Look for `"chat":{"id":694928527,...}` — that number is your chat ID.

## Part C — Verify the token works (before touching the project)

```powershell
curl.exe -s "https://api.telegram.org/bot<PASTE-TOKEN>/getMe"
```

Expect: `"ok":true` and your bot's username. If you see `401 Unauthorized`,
the token is wrong or revoked — back to Part A.

## Part D — Give the token to the project (I will do this with you)

The project keeps secrets in the untracked `.env` file at the repo root.
The safe procedure (performed by the agent, never committing the file):

1. **Backup first**: `.env` → `.env.bak-YYYYmmdd-HHMMSS`
2. **Patch by key-prefix rewrite** — only the `TELEGRAM_BOT_TOKEN=` line
   changes; every other key is preserved byte-for-byte.
3. **Masked verification**: `getMe` is probed through a script that prints
   only the first 6 and last 4 characters of the token, never the whole.
4. The Settings model also expects:
   - `TELEGRAM_CHAT_ID=694928527` (numeric, no `@`)
   - `TELEGRAM_ADMIN_IDS=["694928527"]` (JSON array of numbers)
5. **Hard rule of this codebase**: a placeholder/invalid token makes the
   system **refuse to start on purpose** (`InvalidToken` abort). This is a
   safety design — a trading system must never run silent without alerts.

## Part E — Revive the P5 supervisor (the standing 02Oct procedure)

Current live state (verified 02Oct 21:4x IST): the old token is dead
(HTTP 401), the system aborted two fresh-starts (`unhandled_exceptions=1`
each), and the revive-only watchdog (`LOATS_P5_Watchdog`, every 5 minutes)
cannot heal it while supervisor pid 9324 lives. The ordered steps once the
new token exists:

1. Masked `getMe` → expect `ok:true`.
2. Backup `.env` (timestamped), patch the `TELEGRAM_BOT_TOKEN` line.
3. Stop the wedged supervisor (pid 9324) so the resume slot frees.
4. Wait ≤ 5 minutes — `LOATS_P5_Watchdog` fires and **fresh-starts** a new
   span (per ADR-006 / R-16: the watchdog is revive-only; the fresh start
   begins a new 14-day accumulation clock at the new span's `started_at`).
5. **Green read-back** (all must be true):
   - new `reports/p5_forward_test_*.json` with `ended_at: null`
   - `kill_switch_verified: true` at supervision start
   - `unhandled_exceptions: 0`
   - routing `enabled_at_start: true`
   - log window clean of `InvalidToken` / `token ... rejected`
6. Optional end-to-end probe through the app's own sender
   (`AlertSystem._initialize_bot()` then `send_alert(...)` → `True`).
   Note: alerts dedupe per type for 300 s — repeat probes need a new type.

## Part F — What happens after (no action needed from you)

- The supervisor runs `scripts/run_p5_forward_test.py --resume` and keeps
  the span alive across reboots (scheduled task `LOATS_P5_Resume` wraps it
  at logon; `LOATS_P5_Status` reports daily at 09:00).
- **Token rotation in future = the same Part D/E.** A running process
  keeps its startup token until it restarts; rotation is not live until
  the restart happens (scheduled around open trading positions).

---

### Cheat sheet

| Thing | Value / where |
|---|---|
| Bot creator chat | `@BotFather` → `/newbot` |
| Token format | `digits:AA...` — treat like a password |
| Your chat ID | numeric (verify via `getUpdates` after START) |
| Project files | `.env` (untracked) read by `src/loats/config/settings.py` |
| Sender class | `AlertSystem` in `src/loats/alerts.py` |
| Kill command | the admin allow-list (`TELEGRAM_ADMIN_IDS`) gates it |
| Watchdog | scheduled task `LOATS_P5_Watchdog`, every 5 min |
