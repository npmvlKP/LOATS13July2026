# WhatsApp Bot — Beginner's Guide for LOATS
(Reality first: the project has NO WhatsApp support today — zero WhatsApp
references exist in the code. Everything below is how to add it safely,
what it costs, and what it does NOT do.)

## Why this is harder than Telegram

| | Telegram | WhatsApp |
|---|---|---|
| Bot creation | Free, 2 min, in-app (@BotFather) | Business Platform (Meta) — needs business verification, phone number, token via Meta's dashboard |
| Cost | Free | Free tier: 1,000 free service conversations/month; marketing/utility conversation charges apply beyond that (Meta pricing, varies by country) |
| Send-first allowed | Yes (after user START) | No — WhatsApp requires the **user to message first** within a 24-hour window; template messages outside it need pre-approved templates |
| Message format | Full HTML | Plain text + minimal formatting (`*bold*`, `_italic_`), no HTML |
| Admin commands (kill switch) | Supported today (`/kill` etc. via admin allow-list) | Possible but must be rebuilt; 24h window rules constrain unsolicited alerts |

## Part A — Create the "bot" (WhatsApp Business Platform, beginner path)

1. Go to **developers.facebook.com** → create a developer account (same
   login as your Meta/Facebook account).
2. **My Apps → Create App** → type **Business**.
3. In the app dashboard find the **WhatsApp** product → "API Setup" page.
4. Meta gives you a **test number** + a temporary access token (24h) —
   good for experiments only. For always-on use you must later add a real
   phone number (a number NOT already on any WhatsApp account; a cheap
   SIM/eSIM or a provider number) and exchange the temp token for a
   **permanent system-user token** (Business Settings → Users → System
   user → generate token with `whatsapp_business_messaging` +
   `whatsapp_business_management` scopes).
5. **Recipient allow-list**: in the API Setup page add your personal
   number as a test recipient (up to 5 free test numbers). Send the
   first message FROM your phone TO the test number ("hello"), because
   send-first is not allowed on WhatsApp.

### A.2 — No-code alternative (if Meta dashboards frighten thee)

Providers like **Twilio API for WhatsApp**, **AiSensy**, **Wati**,
**Interakt** sell hosted WhatsApp API access: you still create the Meta
app + number, they host the integration. Costs monthly rent + Meta's
conversation fees. Honest verdict: for LOATS's alert volume (tens/day)
Meta's own cloud API free tier is the cheapest honest path; the no-code
providers charge for UI conveniences LOATS does not need.

## Part B — Wire it into LOATS (what would actually be built, next wave)

Nothing exists in-repo today. The minimal build is small and honest:

1. **Settings**: add `whatsapp_enabled: bool = False`, `whatsapp_token:
   SecretStr`, `whatsapp_phone_number_id: str`, `whatsapp_recipient: str`,
   default **disabled** — same pattern as Telegram's `SecretStr` fields.
2. **Sender class**: `WhatsAppAlertSystem` mirroring `AlertSystem`:
   a `send_alert(message, alert_type) -> bool` that POSTs to
   `https://graph.facebook.com/v21.0/<PHONE_NUMBER_ID>/messages`
   with `Authorization: Bearer <token>`, body
   `{"messaging_product":"whatsapp","to":recipient,"type":"text",
   "text":{"body":...}}`. Lazy-init like the Telegram bot; structured
   logging; no secrets in logs.
3. **Kill-switch commands**: a WhatsApp inbound webhook would be needed
   for `/kill` over WhatsApp — bigger build (public webhook URL, Meta
   verification, TLS). Recommendation: **keep the kill switch on Telegram
   only**; WhatsApp = alerts out only, until there is a strong reason.
   (SEBI's kill-switch duty does not care which chat app carries it.)
4. **Failure semantics**: WhatsApp send failure must degrade to structured
   logs, never crash the orchestrator (same contract as alerts.py today).
5. WhatsApp is a pure **additive** module — zero changes to existing
   behavior.

## Part B.2 — Intermediate option: WhatsApp Web bridge (NOT recommended for production)

Community bridges (whatsapp-web.js, Baileys) automate a QR-scanned
WhatsApp Web session. No Meta business setup needed, but: it breaks Meta's
ToS, the number can be **banned**, and it is not sanctioned for automated
alerting. If the operator wants a 10-minute experiment on a **throwaway
number**, it demonstrates the pipeline; never wire the trading alert path
to it.

## Part C — Costs and compliance notes

- Conversation-based pricing: service conversations (user-initiated,
  24h window) — 1,000/month free; utility/auth/marketing conversations
  are metered per conversation, price varies by country (Meta pricing
  page is the source of truth; rates changed 01Jul2025).
- For LOATS's alert volume, expect near-zero cost in practice. Alerts OUT
  are business-initiated: either use the free utility-conversation
  allowance, or keep a recent inbound message to open the 24h window.
  **Cheapest honest pattern: you message the bot daily (opens the
  window), it replies within 24h inside the free service conversation.**
- Compliance: WhatsApp carries the same secret-hygiene rules as Telegram
  (token = password; `.env` untracked; masked probes only). SEBI has no
  WhatsApp-specific rule; the alert channel is not a regulated surface —
  the audit trail is, and it stays in-repo regardless of channel.

## Part D — What I need from you (if you say "go")

1. Meta developer account + created Business app + WhatsApp product added
   (Part A steps 1–4).
2. The permanent system-user token (masked probe first, like Telegram).
3. A phone number not attached to any WhatsApp account for the bot.
4. Then I build Part B (settings + sender + tests) as a normal wave:
   branch → gates → PR → CI → merge — everything verified as usual.
