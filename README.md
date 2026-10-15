# AI Reminder Bot (v1)

Personal Telegram reminder agent for 2 users sharing one group chat. See `doc/SolutionDesignv1.md`.

## Setup

1. Create a Telegram bot via @BotFather. Disable privacy: `/setprivacy` -> Disable. Get token.
2. Create Supabase project; run `db/schema.sql` in SQL editor.
3. Copy `.env.example` to environment variables (Vercel dashboard or local `.env`).
4. Deploy to Vercel.
5. Register webhook:
   ```
   curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url":"https://<deployment>/api/webhook","secret_token":"<WEBHOOK_SECRET>"}'
   ```
6. Both users DM `/start`, partner `/join` in group.

## Local dev

```bash
pip install -r requirements.txt
uvicorn api.webhook:app --reload --port 8000
```

Cron endpoint can be triggered manually:
`curl -H "Authorization: Bearer $CRON_SECRET" https://<deployment>/api/cron`
