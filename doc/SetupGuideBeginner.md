# V1 Setup Guide for Beginners

This guide assumes you have never used Supabase, Vercel, or Telegram bots. Follow it in order. Do not skip steps.

## Part 0: What you are building

- A Telegram bot in a private 2-person group.
- Every morning at 6:00 AM (Vietnam time) it posts everyone's tasks in the group.
- You (admin) manage defaults; your partner sends their tasks by DM to the bot.
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

**Supabase seems "asleep"**
- On free tier, projects may pause after inactivity. The daily cron pings the DB, which usually keeps it awake. If paused, open Supabase dashboard to wake it.

**Time looks wrong**
- Cron is fixed at 23:00 UTC = 6:00 AM GMT+7. If you need a different time, change `vercel.json` schedule and redeploy. Use https://crontab.guru (UTC).

Good luck. You now run a $0 personal reminder system.
