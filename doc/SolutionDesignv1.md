# Solution Design v1

## 1. Purpose

A Telegram reminder agent for 2 users (admin + partner) sharing 1 group chat. It supports per-user and shared default reminders plus daily ad-hoc tasks, and posts a single public morning digest to the group.

## 2. Scope

**In scope (v1)**
- Fixed allowlist of 2 Telegram user IDs and 1 group.
- Per-user recurring default reminders.
- Shared group reminders.
- Daily task input via DM (free text, rule-based parser) with confirmation.
- Single public digest in group at 6:00 AM GMT+7.
- Rule-based parsing and simple command flows.
- Minimal admin controls.

**Out of scope (v1)**
- AI/LLM parsing, voice input, done/snooze tracking, multi-timezone, multi-group scaling, DM mirror.

## 3. Architecture

Components:

1. **Bot Gateway (Vercel Python function)** — receives Telegram webhook updates for DMs and groups.
2. **Handlers** — command routing + free-text handling, access control.
3. **Parser (rule-based)** — splits input into candidate tasks + optional times; no LLM.
4. **Storage (Supabase Postgres)** — users, groups, memberships, reminders, daily_tasks, settings.
5. **Scheduler (Vercel Cron)** — single daily tick at 23:00 UTC triggering digest build + send.
6. **Dispatcher** — sends Telegram messages; handles formatting and 4096-char chunking.
7. **Config layer** — env vars for tokens, allowlists, secrets.

Data flow (input): Partner DMs free text → webhook → auth check → parse → candidate reply with confirmation → persist daily_tasks for tomorrow on confirm.

Data flow (digest): Cron → GET /api/cron?secret=… → gather defaults/today tasks → build digest text → sendMessage to group chat → idempotency guard (last_digest_date).

## 4. Tech stack (free)

- Runtime: Python 3.11
- Framework: FastAPI + Mangum (serverless handler)
- Bot lib: python-telegram-bot v21 (async)
- DB: Supabase free Postgres
- Host: Vercel Hobby (webhook + cron)
- Parser: regex/rule-based (no external AI)
- Secrets: Vercel env vars

## 5. Repository layout

```
ai-agent/
├── api/
│   ├── webhook.py        # FastAPI app: POST /api/webhook
│   └── cron.py           # GET /api/cron (secret-guarded)
├── lib/
│   ├── config.py         # env vars
│   ├── db.py             # Supabase client
│   ├── users.py          # upsert users, memberships
│   ├── parser.py         # rule-based parser
│   ├── handlers.py       # command + free-text handlers
│   ├── digest.py         # group digest builder
│   └── tg.py             # send helpers
├── requirements.txt
├── vercel.json
└── .env.example
```

## 6. Data model (Supabase)

```sql
create table users (
  id uuid primary key default gen_random_uuid(),
  tg_user_id bigint unique not null,
  username text,
  display_name text,
  is_admin boolean default false,
  created_at timestamptz default now()
);

create table groups (
  id uuid primary key default gen_random_uuid(),
  tg_group_id bigint unique not null,
  title text,
  digest_time_utc time default '23:00',
  active boolean default true
);

create table memberships (
  user_id uuid references users(id) on delete cascade,
  group_id uuid references groups(id) on delete cascade,
  primary key (user_id, group_id)
);

create table reminders (          -- recurring defaults (per-user or shared)
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,  -- null => shared group reminder
  group_id uuid references groups(id) on delete cascade,
  title text not null,
  time_of_day time,
  weekdays int[] default '{1,2,3,4,5,6,7}',
  active boolean default true
);

create table daily_tasks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  group_id uuid references groups(id) on delete cascade,
  for_date date not null,
  title text not null,
  time_of_day time,
  done boolean default false,
  created_at timestamptz default now()
);

create table settings (
  key text primary key,
  value text
);  -- last_digest_date, owner IDs cache, etc.
```

Notes: shared group reminders have `user_id = null`.

## 7. Access control

- `ALLOWED_USER_IDS` env: comma-separated 2 Telegram user IDs. Only these may use DM features; others receive "not authorized".
- `ALLOWED_GROUP_IDS` env: comma-separated allowed group chat IDs; bot ignores other groups.
- Admin = first ID in allowlist (or `ADMIN_USER_ID`). Only admin manages shared reminders and settings.

## 8. Commands and handlers

| Command | Who | Where | Purpose |
|---|---|---|---|
| /start | both | DM | Register user (upsert users + memberships), show help |
| /join | both | group | Link membership for that group |
| /add <title> <HH:MM> [daily] | both | DM/group | Add personal default reminder |
| /default add/remove/list | both | DM | Manage per-user defaults |
| /default shared ... | admin | DM/group | Manage shared group reminders |
| /tomorrow <text> | both | DM (preferred) | Replace/add tasks for next day |
| /today | both | DM/group | Show today's tasks |
| /list | both | DM | List defaults + today (admin sees all) |
| /settings | admin | DM | Set digest time, allowlists display |
| /help | both | DM/group | Usage help |

Non-command text:
- In DM: treated as **tomorrow input** → parser → confirmation flow.
- In group: only handled if addressed to bot (mention/reply) to avoid noise; defaults to tomorrow input for the sender.

## 9. Parser (rule-based v1)

Input examples:
- `finish report; gym 18:00; call mom`
- `report at 6pm, gym, water 9`
- multi-line lists

Algorithm:
1. Split on `;`, `,`, or newlines into segments.
2. Trim empties.
3. For each segment, extract time via regex:
   - `HH:MM` (24h) or `H:MM am/pm` or `Hpm`/`Ham`.
4. Remaining text = title (strip trailing "at", "on").
5. Drop segments that parse to empty title.
6. Return list `{title, time_of_day (nullable)}`.

Output shown to user as numbered list with extracted times; user confirms or resends edited version. Confirmation modifies nothing until "Yes".

Time normalization uses admin's configured timezone display but stored as `time_of_day` (local wall clock for the group's region, GMT+7). V1 assumes single region (GMT+7).

## 10. Onboarding flow

1. Admin creates group, adds bot + partner.
2. Bot receives `my_chat_member` → creates `groups` row with group chat id/title (only if group in allowlist; if not known yet, admin sets via `/settings` or first `/join`).
3. Admin and partner each DM bot `/start` → upsert `users`; memberships auto-linked if group exists, else linked on `/join`.
4. Admin sets digest time via `/settings` (default 23:00 UTC).
5. Admin disables bot privacy in @BotFather (`/setprivacy` → Disable) so bot can read group messages, or makes bot group admin.

## 11. Daily input flow

1. User sends free text in DM.
2. Handler checks allowlist.
3. Parser produces candidate tasks with times.
4. Bot replies:
   ```
   I understood:
   1. Finish report — 18:00
   2. Gym — (no time)
   
   Save for tomorrow? [Yes] [Edit] [Cancel]
   ```
5. `Yes`: insert into `daily_tasks` with `for_date = tomorrow (GROUP TZ)`; reply count saved.
6. `Edit`: user resends corrected text (re-run parser).
7. `Cancel`: discard.
8. Re-running `/tomorrow` replaces prior candidates? V1: append; admin can delete via `/list` + `/remove`. (Simpler: append.)

## 12. Digest flow

Trigger: Vercel Cron `0 23 * * *` → GET `/api/cron?secret=CRON_SECRET`.
1. Validate secret (constant-time compare).
2. For each active group:
   - If `last_digest_date` == today (UTC date) → skip (idempotency).
   - Compute "today" in group region (GMT+7) = UTC+7 date.
   - Gather per member:
     - Daily reminders active with matching weekday for today.
     - `daily_tasks` for that user where `for_date = today`.
   - Gather shared reminders (`user_id is null`) active with matching weekday.
   - Build message:
     ```
     📋 Today's reminders — <weekday>, <date>

     👤 Admin (@admin)
     • 09:00 Drink water
     • 18:00 Finish report
     • Gym

     👤 Partner (@partner)
     • 07:30 Drink water
     • 19:00 Call mom

     🤝 Shared
     • 20:00 Take out trash

     Send tomorrow's tasks tonight via DM.
     ```
   - Chunk if > 4096 chars (unlikely for 2 users).
   - `sendMessage` to `tg_group_id`.
   - On success set `last_digest_date = today`.
3. Return 200 with summary counts; on partial failure return 207/500 and log.

Retry: if send fails, next day's cron does not retry prior day (V1). Acceptable for personal use. Optional V2: retry window within same day.

Weekday mapping: Postgres `extract(isodow from date)` (1=Monday). Python `date.weekday()` (0=Monday) +1.

## 13. Scheduler configuration

`vercel.json`:
```json
{
  "functions": { "api/*.py": { "runtime": "python3.11" } },
  "rewrites": [{ "source": "/api/(.*)", "destination": "/api/$1" }],
  "crons": [{ "path": "/api/cron", "schedule": "0 23 * * *" }]
}
```

Vercel Hobby supports up to 2 cron jobs. Only one needed. Secret passed as query param and validated server-side; Vercel cron can't set headers easily, so query secret is acceptable for personal use (keep URL private).

## 14. Webhook setup

- Register webhook URL with Telegram: `https://<deployment>/api/webhook?secret=WEBHOOK_SECRET` or set `secret_token` via `setWebhook` and validate `X-Telegram-Bot-Api-Secret-Token` header (preferred). V1 uses header-based secret for stronger validation.
- Handle duplicate update_ids: track last processed update_id in settings or ignore via Telegram's own dedupe (best-effort; idempotent handlers).

## 15. Environment variables

```
BOT_TOKEN=
WEBHOOK_SECRET=
CRON_SECRET=
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
ALLOWED_USER_IDS=123,456
ALLOWED_GROUP_IDS=-100...
ADMIN_USER_ID=123
GROUP_TIMEZONE=Asia/Bangkok   # GMT+7
```

## 16. Deployment steps

1. Create bot via @BotFather; get token; `/setprivacy` disable.
2. Create Supabase project; run schema; copy URL + service key.
3. Create Vercel project; set env vars; deploy.
4. `setWebhook` to deployment URL with secret token.
5. Admin/partner DM `/start`; partner `/join` in group (or auto-link).
6. Admin `/settings` to confirm digest time.
7. Wait for first cron tick or manually call `/api/cron?secret=...` to test.

## 17. Cost

- Telegram Bot API: $0.
- Vercel Hobby: $0 (webhook + 1 cron).
- Supabase free: $0 (tiny data).
- LLM: none (rule-based).
- Total: **$0/month**.

## 18. Risks and mitigations

- **Cold start (1–3s)**: Telegram retries; handlers idempotent; acceptable for personal use.
- **Supabase free auto-pause** (7 days inactivity): daily cron touches DB → keeps active.
- **Telegram spam/rate limits**: single digest/day, 2 users → no issue; chunk messages.
- **Input ambiguity**: confirmation step before persisting; no data written on parse-only.
- **Bot cannot read group messages** if privacy on: disable privacy or make admin.
- **Secret leakage in cron URL**: prefer header for webhook; cron query secret acceptable for personal scale but keep URL private.
- **Date/time off by one**: group timezone fixed GMT+7; document; admin verifies.
- **Duplicate update delivery**: best-effort idempotent handlers.

## 19. Testing (manual)

- DM `/start` as both users; verify rows.
- `/join` in group; verify membership.
- Send free text in DM; confirm parse + persistence; verify `/today`.
- Shared reminder `/default shared add "test" 23:59 *` then manually trigger cron; verify digest.
- Trigger cron twice same day; verify skip (idempotency).
- Unauthorized user DMs bot; verify rejection.

## 20. Success criteria

- Both users can manage own tasks via DM.
- Admin can manage shared reminders.
- Daily digest arrives in group at 6 AM GMT+7 with correct combined content.
- No cost and no scaling concerns for 2-user use.
