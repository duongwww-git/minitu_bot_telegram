# Setup Guide for Beginners

This guide assumes you have never used Supabase, Vercel, or Telegram bots. Follow it in order. Do not skip steps.

## Part 0: What you are building

- A Telegram bot in a private 2-person group.
- Every morning at 6:00 AM (Vietnam time) it posts everyone's tasks in the group.
- You (admin) manage defaults; your partner sends their tasks by DM to the bot.
- Optional (v2, Part 12): add tasks by voice note or natural language, using Google Gemini (free tier).
- Cost: $0.

## Part 1: Get your Telegram user ID

Your user ID is a number like `123456789`. The bot uses it to know who you are.

1. Open Telegram on phone or desktop.
2. Search for `@userinfobot`.
3. Press **Start**.
4. The bot replies. Look for a line like `Id: 123456789`.
5. Write this number down. This is **your user ID**.
6. Ask your partner to do the same and send you their ID.
7. You now have two numbers, e.g. `123456789, 987654321`.

## Part 2: Create the Telegram bot

1. Open Telegram.
2. Search for `@BotFather` (official, blue checkmark).
3. Press **Start**.
4. Send this message: `/newbot`
5. BotFather asks for a name. Type something like `Our Task Reminder`. Press Enter.
6. BotFather asks for a username. It must end in `bot`. Type something like `our_task_reminder_xyz_bot`. Press Enter.
7. BotFather replies with a token, a long string like `1234567890:ABCdef...`. **Save it safely.** This is `BOT_TOKEN`.
8. Disable group privacy so the bot can read group messages:
   a. Send `/mybots` to BotFather.
   b. Click your bot.
   c. Click `Bot Settings`.
   d. Click `Group Privacy`.
   e. Click `Turn off`.
   f. Confirm.
9. Create a new group in Telegram with you, your partner, and this bot. Add the bot to the group.

## Part 3: Create the database in Supabase

Supabase stores your tasks and settings.

1. Open a browser, go to https://supabase.com.
2. Click `Start your project`.
3. Sign up (free) with GitHub or email.
4. After login, click `New project`.
5. Choose an organization (create one if needed).
6. Fill:
   - Project name: `reminder-bot` (or anything)
   - Database password: create a strong password, save it
   - Region: choose one close to you (e.g. Singapore)
7. Click `Create new project`. Wait 1–2 minutes.
8. On the project dashboard, left sidebar, click `SQL Editor`.
9. Click `New query`.
10. Open the file `db/schema.sql` from your repo on your computer (use any text editor).
11. Copy all the text in that file.
12. Paste it into the Supabase SQL Editor.
13. Click `Run` (top right).
14. You should see a success message. Click `Table Editor` (left sidebar) to confirm tables exist: `users`, `groups`, `memberships`, `reminders`, `daily_tasks`, `settings`, `conversation_state`.
15. Get credentials:
    a. Left sidebar -> `Project Settings` (gear) -> `API`.
    b. Under "Project URL", copy it. This is `SUPABASE_URL`.
    c. Under "Project API keys", find `service_role` (secret) and click `Reveal`. Copy it. This is `SUPABASE_SERVICE_ROLE_KEY`. Never share it publicly.

## Part 4: Prepare the code on GitHub (recommended)

You need to deploy the code. Easiest is via GitHub + Vercel.

1. Create a GitHub account at https://github.com if you don't have one.
2. Create a new repository, e.g. `telegram-reminder-bot`. Keep it private.
3. Upload all files from `ai-agent` folder to the repo:
   - Option: install GitHub Desktop, drag the folder, commit, push.
   - Or use git commands:
     ```bash
     cd /Users/duongwww/repos/ai-agent
     git init
     git add .
     git commit -m "v1"
     git branch -M main
     git remote add origin https://github.com/YOUR_USERNAME/telegram-reminder-bot.git
     git push -u origin main
     ```
4. Confirm files appear on GitHub.

## Part 5: Deploy on Vercel

1. Go to https://vercel.com and sign up (use GitHub login).
2. Click `Add New...` -> `Project`.
3. Import your GitHub repository.
4. Leave build settings as default. Click `Deploy`.
   - It may succeed even without env vars; you'll add them next.
5. After deploy, Vercel gives you a URL like `https://telegram-reminder-bot-xxx.vercel.app`. Save it.

## Part 6: Add environment variables in Vercel

In Vercel dashboard, open your project -> `Settings` -> `Environment Variables`.

Add each variable below. For each, type name, value, environment = Production (and Preview if asked), then click `Save/Add`.

Variables:

1. `BOT_TOKEN` = token from BotFather
2. `WEBHOOK_SECRET` = a long random string. You can create one in Terminal:
   ```bash
   openssl rand -hex 32
   ```
   Copy the output.
3. `CRON_SECRET` = run the same command again and copy a *different* string.
4. `SUPABASE_URL` = Project URL
5. `SUPABASE_SERVICE_ROLE_KEY` = service role secret
6. `ALLOWED_USER_IDS` = `123456789,987654321` (your two IDs, no spaces)
7. `ALLOWED_GROUP_IDS` = your group ID. To find it:
   - Open your group in Telegram.
   - Add `@RawDataBot` to the group temporarily.
   - It sends the group info; look for "id": `-100...`. Copy that number.
   - Remove `@RawDataBot` from the group.
   - If you don't have the group ID yet, you can deploy first and set it later; for now put the ID if you have it.
8. `ADMIN_USER_ID` = your own user ID (the admin one).
9. `BOT_USERNAME` = bot username without `@`, e.g. `our_task_reminder_xyz_bot`.
10. `GROUP_TIMEZONE` = `Asia/Bangkok`
11. `DIGEST_HOUR_LOCAL` = `6`

Optional v2 (AI + voice) — add these only if you want Gemini features (full walkthrough in Part 12):

12. `GEMINI_API_KEY` = API key from https://aistudio.google.com/apikey (free tier, no credit card). Needed for voice; also enables AI text parsing. Full walkthrough in Part 12A.
13. `AI_MODEL_TEXT` = `gemini-3.8-flash`
14. `AI_MODEL_TRANSCRIBE` = `gemini-3.5-transcribe`
15. `USE_AI` = `false` (set `true` to parse free text with Gemini; the rule parser is used otherwise)
16. `VOICE_QUEUE_MAX` = `5`
17. `VOICE_DRAIN_MAX` = `3`
18. `VOICE_RETRY_TTL_HOURS` = `48`

After adding all, go to `Deployments` -> click the three dots on latest deployment -> `Redeploy`. Confirm.

## Part 7: Register the webhook with Telegram

This tells Telegram to send messages to your Vercel app.

1. Open Terminal (macOS: press Cmd+Space, type `Terminal`).
2. Replace the placeholders and run:

```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://YOUR-VERCEL-URL.vercel.app/api/webhook","secret_token":"<WEBHOOK_SECRET>"}'
```

Example (fill real values):

```bash
curl -X POST "https://api.telegram.org/bot123456:ABC/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://telegram-reminder-bot-abc.vercel.app/api/webhook","secret_token":"abc123secret"}'
```

3. You should see `{"ok":true,...}`.
4. Check status:
```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
```
Look for `"url"` and no errors.

## Part 8: First test

1. You and your partner open a private chat with the bot.
2. Each sends `/start`.
   - You (admin): should see "Registered. Admin."
   - Partner: "Registered. User."
3. In the group chat, admin or partner sends `/join`.
   - Should say "Linked to group."
4. Each person DMs the bot:
   ```
   /tomorrow finish report; gym 18:00; call mom
   ```
5. Bot replies with parsed list and buttons: Save / Edit / Cancel.
6. Press **Save**.
7. Send `/list` in DM. You should see defaults and today's tasks.

## Part 9: Test the morning digest immediately

Don't wait until 6 AM. Trigger the cron manually:

```bash
curl -H "Authorization: Bearer <CRON_SECRET>" "https://YOUR-VERCEL-URL.vercel.app/api/cron"
```

Expected response:
```json
{"ok":true,"today_local":"...","sent":1,"skipped":0,"errors":[]}
```

Check your Telegram group: a digest message should appear listing both users' tasks.

Run the same command again:
- Response should show `"skipped":1` and no second message. This means duplicate protection works.

## Part 10: Add shared reminders (optional)

In the group chat (admin only), send:
```
/default shared add Take out trash 20:00
/default shared list
```

Or in DM (admin):
```
/default shared add Pay rent 09:00
```

## Part 11: You're done

From now on:
- Every evening, send tasks via DM using `/tomorrow ...` (or free text in DM).
- Every morning at 6 AM (Vietnam time), the bot posts the digest in the group.

## Part 12: Enable AI and voice (optional, v2)

This part is optional — skip it if you only want the rule-based bot from Parts 1–11.

With Gemini enabled you get:

- **Voice input**: send a voice note in DM and the bot turns it into tasks.
- **Smarter text parsing** (only when `USE_AI=true`): free text like `mua sua, goi dien cho me chieu nay` is parsed by AI, with the rule parser as a fallback.

Cost: **$0** at this scale. The Gemini free tier does not require a credit card.

### Part 12A: Get your GEMINI_API_KEY

You create the key in **Google AI Studio**, Google's free developer console for Gemini.

1. Open a browser and go to: https://aistudio.google.com/apikey
2. Sign in with any Google account (a normal Gmail works).
   - First time only: accept the terms of service if a dialog appears.
3. Click **Create API key** (top right; it may say **Get API key** first).
4. If it asks you to choose a Google Cloud project:
   - Choose **Create new project**.
   - Name it something like `minitu-bot`, then confirm.
   - Wait a few seconds while Google creates it.
5. A key appears, starting with `AIza...` (about 39 characters). Click **Copy**.
   - Save it somewhere safe immediately — a password manager, or a private note. Treat it like a password.
   - ⚠️ Vercel masks the value after saving and cannot show it again. If you lose it, you'll create a new key (this page), not recover the old one.
6. Optional: confirm you are on the free tier. The same page shows rate limits. At the time of writing, the free tier covers Flash and Transcribe models at roughly **10–15 requests per minute** — far more than two people will ever use.

Gotchas:

- Never paste the key into a group chat, GitHub, a screenshot, or this repo. If it leaks, delete it on this page and create a new one.
- If **Create API key** is greyed out, make sure you are on the **API keys** page (the link above), not on AI Studio's chat page.
- If your Google account is managed by a workplace or school, your admin may block API keys. Use a personal Gmail account instead.
- If Google asks for a credit card, you went to the paid Google Cloud console. Go back to the AI Studio link above — no billing is needed.

### Part 12B: Add the key to Vercel

1. Open https://vercel.com and select your bot project.
2. Go to **Settings** (top menu) → **Environment Variables** (left sidebar).
3. Add the key:
   - **Key**: `GEMINI_API_KEY`
   - **Value**: paste the `AIza...` key from Part 12A
   - **Environments**: tick **Production** (and Preview if you like)
   - Click **Save**.
4. (Optional) Add the other v2 variables while you are here — the defaults below are fine:
   - `AI_MODEL_TEXT` = `gemini-3.8-flash`
   - `AI_MODEL_TRANSCRIBE` = `gemini-3.5-transcribe`
   - `USE_AI` = `true` to enable AI text parsing, or `false` to keep the rule parser (voice works either way)
   - `VOICE_QUEUE_MAX` = `5`
   - `VOICE_DRAIN_MAX` = `3`
   - `VOICE_RETRY_TTL_HOURS` = `48`
5. Redeploy so the new variables take effect:
   - Go to **Deployments** → click the three dots (`...`) on the latest deployment → **Redeploy** → confirm.
   - Vercel only applies environment changes to a **new** deployment.
6. Verify the key loaded. In Terminal, run (replace with your URL):

   ```bash
   curl "https://YOUR-VERCEL-URL.vercel.app/api/debug"
   ```

   Look for:
   - `"gemini_key_set": true`
   - `"voice_enabled": true`
   - `"use_ai": true` (only if you set `USE_AI=true`)

   If `gemini_key_set` is `false`, the variable name is misspelled, or the redeploy hasn't finished.

### Test it

1. Open a DM with your bot and send a voice note, e.g. "di gym luc 6 gio chieu nay".
   - Expected: a reply starting with `📝 Transcript: ...`, then the parsed task list with **Save / Edit / Cancel**.
2. If you set `USE_AI=true`, send a normal DM message, e.g. `mua sua, goi dien cho me`.
   - Expected: Gemini parses it first; if the AI call fails, the bot still replies using the rule parser.
3. In the group, voice notes are only read when you **reply to one of the bot's messages** (so ordinary group chatter isn't transcribed). DMs always work.

### What if transcription is busy (free-tier rate limit)?

The Gemini free tier allows only a few requests per minute. If you send voice notes too quickly:

- The bot replies: `Transcription is busy. Recordings saved: N. Tap Retry or send /retry.`
- Your recordings are queued (up to 5). Tap the **🔁 Retry** button, or send `/retry`.
- `/retry` also works while replying to a voice message, even after the queue expired.
- Nothing is lost: the bot keeps a reference to each recording for 48 hours, so you never have to re-send the audio.

## Common problems

**Bot doesn't reply at all**
- Webhook not registered: repeat Part 7.
- Wrong `WEBHOOK_SECRET`: Vercel env must exactly match the token in `setWebhook`. Redeploy after changing.

**"Not authorized"**
- User ID not in `ALLOWED_USER_IDS`, or there are spaces. Fix env var and redeploy.

**Group not allowed / commands in group fail**
- `ALLOWED_GROUP_IDS` wrong. Use `@RawDataBot` to get the `-100...` ID.

**Bot can't read group messages**
- Privacy not turned off in BotFather. Turn it off, remove and re-add bot to group.

**No digest appears on manual cron**
- Response `errors` will tell you. Common causes:
  - No group linked (run `/join` in group).
  - No tasks or reminders for today.
  - `ALLOWED_GROUP_IDS` not set; bot doesn't know which group (check env).
- Check Supabase `memberships` table to ensure both users are linked.

**Voice note not transcribed**
- `GEMINI_API_KEY` missing or wrong: the bot replies "Voice input isn't enabled on this bot". Add the key and redeploy.
- Free-tier rate limit: the bot queues the note and shows a Retry button. Tap it or send `/retry` after a minute.
- Never sends a transcript: the recording may be too long or quiet; try a shorter note.

**Supabase seems "asleep"**
- On free tier, projects may pause after inactivity. The daily cron pings the DB, which usually keeps it awake. If paused, open Supabase dashboard to wake it.

**Time looks wrong**
- Cron is fixed at 23:00 UTC = 6:00 AM GMT+7. If you need a different time, change `vercel.json` schedule and redeploy. Use https://crontab.guru (UTC).

**Vercel says "No FastAPI entrypoint found" or references `api/*.py`**
- The repo was updated to a single `app.py` entrypoint. If Vercel still mentions old `api/webhook.py` or `api/cron.py` files, your deployment is stale.
- Commit and push all changes:
  ```bash
  cd /Users/duongwww/repos/ai-agent
  git add .
  git commit -m "Use app.py entrypoint"
  git push
  ```
- In Vercel, open your project -> `Deployments` -> `Redeploy` (or wait for the GitHub-triggered deploy).
- Confirm `pyproject.toml` exists with `[tool.vercel] entrypoint = "app:app"`.
- If the error persists, clear Vercel's cache by deleting the project and importing the repo again, or deploy with the CLI from the project root:
  ```bash
  vercel --prod --force
  ```


Good luck. You now run a $0 personal reminder system.
