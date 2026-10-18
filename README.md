# AI Reminder Bot (v2)

Personal Telegram reminder agent for 2 users sharing one group chat. V1 is the
rule-based core; V2 adds Google Gemini intelligence (text parsing + voice
transcription). See `doc/SolutionDesignv1.md` and `doc/SolutionDesignv2.md`.

## Features

- DM tasks (text or voice) from both users; one public digest at 6:00 AM GMT+7.
- Rule-based parser by default; set `USE_AI=true` (plus a `GEMINI_API_KEY`) to
  parse free text with Gemini Flash first, falling back to the rule parser.
- Voice notes in DM are transcribed with Gemini Transcribe, then parsed.
- If transcription is rate-limited, recordings are queued (max 5) and can be
  retried with the **🔁 Retry** button or `/retry`.

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

## AI / voice notes

- `USE_AI=false` (default) preserves the v1 rule-based behavior exactly.
- Voice input requires `GEMINI_API_KEY`; transcription runs even when
  `USE_AI=false` (the transcript then goes through the rule parser).
- The voice retry queue reuses the `conversation_state` table — no migration needed.
