# AI Reminder Bot (v2.1)

Personal Telegram reminder agent for 2 users sharing one group chat. V1 is the
rule-based core; V2 adds Google Gemini intelligence (text parsing + voice
transcription); V2.1 adds date detection and quick date moves. See
`doc/SolutionDesignv1.md` and `doc/SolutionDesignv2.md`.

## Features

- DM tasks (text or voice) from both users; one public digest at 6:00 AM GMT+7.
- Rule-based parser by default; set `USE_AI=true` (plus a `GEMINI_API_KEY`) to
  parse free text with Gemini Flash first, falling back to the rule parser.
- Name a day and the task is saved for that date: `today`, `mai`, `ngày mốt`,
  `thứ 6`, `cuối tuần`, `20/10`, `ngày 20 tháng 10`. Without a day it defaults to
  tomorrow. A past date falls back to tomorrow and tells you.
- On the confirmation, a **📅 Move to today / tomorrow** button re-dates the
  batch. A single date moves on the tap; mixed dates ask which tasks by number
  (`1, 3`, `1-3`, `all`), and the reply both moves and saves them.
- Voice notes in DM are transcribed with Gemini Transcribe, then parsed.
- Every Gemini call retries once on a 5xx/timeout and then falls back through an
  ordered model list (`AI_MODEL_TEXT_FALLBACKS` /
  `AI_MODEL_TRANSCRIBE_FALLBACKS` in `config.defaults.json`), so a "high demand"
  503 on one model no longer loses the message.
- If transcription is rate-limited or every model is busy, recordings are queued
  (max 5) and can be retried with the **🔁 Retry** button or `/retry`.
- `/list` shows your tasks from today forward, grouped by date.

## Setup

1. Create a Telegram bot via @BotFather. Disable privacy: `/setprivacy` -> Disable. Get token.
2. Create Supabase project; run `db/schema.sql` in SQL editor.
3. Copy `.env.example` to environment variables (Vercel dashboard or local `.env`).
4. (Optional, for AI/voice) Create a Google AI Studio API key and set `GEMINI_API_KEY`,
   then set `USE_AI=true` to enable AI text parsing.
5. Deploy to Vercel.
6. Register webhook:
   ```
   curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url":"https://<deployment>/api/webhook","secret_token":"<WEBHOOK_SECRET>"}'
   ```
7. Both users DM `/start`, partner `/join` in group.

## Local dev

```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

Cron endpoint can be triggered manually:
`curl -H "Authorization: Bearer $CRON_SECRET" https://<deployment>/api/cron`

## Configuration

Two kinds of settings:

- **Secrets** (`BOT_TOKEN`, `WEBHOOK_SECRET`, `CRON_SECRET`, `SUPABASE_URL`,
  `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`) — env vars only, never committed.
- **Non-secret tunables** (`AI_MODEL_TEXT`, `AI_MODEL_TRANSCRIBE`, `USE_AI`,
  `VOICE_QUEUE_MAX`, `VOICE_DRAIN_MAX`, `VOICE_RETRY_TTL_HOURS`, `UPCOMING_DAYS`,
  `GROUP_TIMEZONE`, `DIGEST_HOUR_LOCAL`) — defaults live in the committed
  `config.defaults.json`. Edit that file instead of Vercel.

Precedence: **env var > `config.defaults.json` > built-in default**. So a Vercel
env var still overrides the file when needed. `/api/debug` reports
`config_file_loaded` plus the effective AI/voice settings.

## AI / voice notes

- `USE_AI=false` (default) preserves the v1 rule-based behavior exactly.
- Voice input requires `GEMINI_API_KEY`; transcription runs even when
  `USE_AI=false` (the transcript then goes through the rule parser).
- The voice retry queue reuses the `conversation_state` table — no migration needed.
