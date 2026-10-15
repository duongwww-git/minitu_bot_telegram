# Solution Design v2 (Draft)

Status: Draft. V2 evolves V1 with intelligence, convenience, and modest scaling while aiming to stay low-cost (target <$5/month for 2–10 users).

## 1. Goals for V2

- Replace/augment rule parser with AI natural-language understanding.
- Add voice input.
- Add done/snooze tracking with inline interactions.
- Optional DM mirror of digest.
- Per-user timezones and smarter scheduling.
- Support more users/groups without redesign.
- Conversation state for multi-turn clarification.

## 2. What changes vs V1

| Area | V1 | V2 |
|---|---|---|
| Parser | Rule-based regex | AI (Groq free / OpenRouter) with structured JSON output + rule fallback |
| Input modalities | Text | Text + voice (Whisper) |
| Task lifecycle | Create only | Create, done, snooze, defer, delete |
| Digest delivery | Group only | Group + optional DM mirror |
| Scheduling | Single UTC cron | Per-user TZ, multiple quiet hours, catch-up |
| Conversation | One-shot confirm | Multi-turn clarification state |
| Scale | 2 users, 1 group | Many users/groups with row-level ownership |
| Observability | Basic logs | Structured logs, error alerts, metrics |

## 3. Proposed architecture additions

- **AI Service module** (`lib/ai.py`): wraps Groq/OpenRouter; function calling to produce `{tasks:[{title,time,priority,recurring?}]}`; validates schema; falls back to rule parser on failure/timeout.
- **Transcription module** (`lib/voice.py`): Telegram voice → download file → Whisper API → text → AI/rule parser.
- **Conversation state store**: `conversation_state(user_id, chat_id, state_json, updated_at)` persists clarification step and pending candidates; expires after N minutes.
- **Task lifecycle endpoints**: callbacks on inline buttons (`done:<id>`, `snooze:<id>:<minutes>`, `skip:<id>`).
- **Scheduler v2**: per-group digest hour in local TZ converted to UTC internally; queue of due digests; retry window same day; catch-up missed ticks.
- **Delivery preferences**: `notification_prefs(user_id, dm_mirror boolean, quiet_hours)`.

## 4. Data model extensions (over V1)

```sql
create table conversation_state (
  user_id uuid references users(id) on delete cascade,
  chat_id bigint not null,
  state jsonb not null,
  updated_at timestamptz default now(),
  primary key (user_id, chat_id)
);

-- reminders/daily_tasks: add column priority int default 0, recurrence text (rrule optional later)
-- users: add timezone text default 'Asia/Bangkok'
-- groups: digest_time_local time, timezone text
-- new:
create table task_events (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null,
  task_type text not null, -- 'reminder' | 'daily_task'
  user_id uuid references users(id),
  action text not null,     -- 'created','done','snoozed','skipped','deleted'
  meta jsonb,
  at timestamptz default now()
);

create table notification_prefs (
  user_id uuid primary key references users(id) on delete cascade,
  dm_mirror boolean default false,
  quiet_start time,
  quiet_end time
);
```

## 5. AI prompt design (outline)

- Input: raw user text + current datetime in user TZ + user's recent task history.
- Output: strict JSON schema: `{tasks:[{title,time (HH:MM|null),priority (1-3),notes?}]}`.
- Rules: no hallucinated tasks; if time ambiguous, return `clarify` with question instead of guessing.
- Safety: cap output length; fallback to rule parser if JSON invalid.
- Cost: Groq free tier for parsing; use small context; cache normalized phrases? Optional.

## 6. Voice flow (outline)

1. User sends voice note to bot (DM preferred; group optional).
2. Webhook detects `message.voice` → download via Bot API → size guard (e.g. <= 60s).
3. Transcribe with Whisper (OpenAI or local) → text.
4. Feed text into parser flow + confirmation.
5. Reply includes transcript preview for correction.

## 7. Done/snooze flow (outline)

- Digest message includes inline buttons per task: ✅ Done, ⏰ +30m, ⏭ Skip.
- Callback query handler updates `daily_tasks.done` / creates snoozed copy with future time.
- Bot edits digest message to strike through completed tasks (or reply with ✅).
- All actions logged to `task_events`.

## 8. Scheduling v2 (outline)

- Store digest time in local TZ per group/user.
- Cron tick every 5–15 minutes (Vercel cron min 1 min; use 5 min if needed) instead of single daily tick.
- Dispatcher queries groups/users whose local digest time falls in the current window and not yet sent today.
- Idempotency via `last_digest_date` per group + per-user DM mirror.
- Retry missed digests on next tick within same day.

## 9. Scaling considerations

- Add pagination/batching for large groups (chunk messages).
- Rate-limit outgoing messages (30 msg/s global; per-chat 1/sec).
- Keep handlers stateless; conversation state in DB.
- Multi-tenant: users/groups tables already scoped; add RLS in Supabase when moving beyond fixed allowlists.
- Self-serve onboarding beyond 2 users: `/start` registers, admin approval optional.

## 10. Migration plan V1 → V2

1. Add new columns/tables via migrations; keep backward compatible.
2. Keep rule parser as fallback behind `USE_AI` flag; AI off by default.
3. Add timezone column defaulting to `Asia/Bangkok` for existing rows.
4. Enable features via flags per user/group to pilot.
5. Gradually enable AI/voice/done-tracking.

## 11. Cost estimate V2 (2–10 users)

- Supabase free: still $0 at this scale.
- Vercel Hobby: $0; if cron frequency needs exceed limits, move scheduler to GitHub Actions (free) or a $5 VPS.
- AI parsing (Groq free): $0 under free limits; if exceeded, ~$1–3/mo with cheap models.
- Whisper (~$0.006/min): negligible for occasional voice.
- Total target: **$0–5/month**.

## 12. Open items for V2

- Choice of LLM provider final (Groq vs OpenRouter vs OpenAI).
- Voice privacy/storage policy (delete audio after transcription).
- Snooze UX and limits.
- Whether to store task history indefinitely or rotate.
- Self-serve user onboarding and admin approval.
- Whether to add a minimal web admin UI.

## 13. Not in V2 (deferred)

- Native mobile app.
- Full NLP sentiment/personality.
- Calendar integrations (Google/Apple).
- Payments/billing.
- Multi-region data residency.
