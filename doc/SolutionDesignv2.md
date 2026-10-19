# Solution Design v2 (Draft)

Status: Draft. V2 evolves V1 with intelligence, convenience, and modest scaling while aiming to stay low-cost (target <$5/month for 2–10 users).

## 1. Goals for V2

- Replace/augment rule parser with AI natural-language understanding (Google Gemini Flash, free tier).
- Add voice input (Google Gemini Transcribe, free tier).
- Add done/snooze tracking with inline interactions.
- Optional DM mirror of digest.
- Per-user timezones and smarter scheduling.
- Support more users/groups without redesign.
- Conversation state for multi-turn clarification.
- English UI/parsing copy in V2 (Vietnamese localization deferred to V3).

## 2. What changes vs V1

| Area | V1 | V2 |
|---|---|---|
| Parser | Rule-based regex | AI (Gemini Flash) with structured JSON output + rule fallback |
| Input modalities | Text | Text + voice (Gemini Transcribe) |
| Task lifecycle | Create only | Create, done, snooze, defer, delete |
| Digest delivery | Group only | Group + optional DM mirror |
| Scheduling | Single UTC cron | Per-user TZ, multiple quiet hours, catch-up |
| Conversation | One-shot confirm | Multi-turn clarification state |
| Language | English | English UI/parsing copy (Vietnamese deferred to v3) |
| Scale | 2 users, 1 group | Many users/groups with row-level ownership |
| Observability | Basic logs | Structured logs, error alerts, metrics |

## 3. Proposed architecture additions

- **AI Service module** (`lib/ai.py`): wraps Google Gemini Flash; structured JSON output to produce `{tasks:[{title,time,priority,recurring?}]}`; validates schema; falls back to rule parser on failure/timeout.
- **Transcription module** (`lib/voice.py`): Telegram voice → download file (`getFile`) → Gemini Transcribe → text → AI/rule parser; rate-limited transcriptions are queued for retry (see §6.5).
- **Conversation state store**: `conversation_state(id, user_id, chat_id, state jsonb, expires_at, created_at)` persists clarification step, pending candidates, and the voice retry queue; expires after N minutes (48h for queued voices).
- **Message catalog** (`lib/messages.py`): centralize all user-facing copy (help text, confirmations, digest labels, voice retry/status messages) so wording and future localization (v3 Vietnamese) live in one place; V1 copy currently lives in `lib/handlers.py` / `lib/digest.py`.
- **Task lifecycle endpoints**: callbacks on inline buttons (`done:<id>`, `snooze:<id>:<minutes>`, `skip:<id>`).
- **Scheduler v2**: per-group digest hour in local TZ converted to UTC internally; queue of due digests; retry window same day; catch-up missed ticks.
- **Delivery preferences**: `notification_prefs(user_id, dm_mirror boolean, quiet_hours)`.

## 4. Data model extensions (over V1)

```sql
-- conversation_state already exists in V1 with this shape (no migration needed):
create table conversation_state (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  chat_id bigint not null,
  state jsonb not null,
  expires_at timestamptz not null,
  created_at timestamptz default now()
);
-- Voice retry queue reuses this table: one row per pending recording with
-- state = {"kind":"pending_voice","file_id":…,"message_id":…,"duration":…,"status":"queued"}.

-- reminders/daily_tasks: add column priority int default 0, recurrence text (rrule optional later)
-- daily_tasks.for_date (date) and .time_of_day (time) already exist in V1, so v2.1 date
-- detection needs no migration; a task is simply stored with the date it names.
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

- Input: raw user text + current *local* datetime (`GROUP_TIMEZONE`) + weekday + user's recent task history.
- Output: strict JSON schema: `{tasks:[{title,time (HH:MM|null),date (YYYY-MM-DD|null),priority (1-3),notes?}]}`.
- Rules: no hallucinated tasks or dates; if time ambiguous, return `clarify` with question instead of guessing.
- Safety: cap output length; validate dates (`_clean_date`); fallback to rule parser if JSON invalid.
- Cost: Gemini Flash free tier for parsing; use small context; cache normalized phrases? Optional.

## 6. AI architecture (two slots) — Google Gemini

### 6.1 Slots

| Slot | Capability | Model | Where |
|---|---|---|---|
| A | Natural-language understanding (text → tasks) | Gemini Flash (`gemini-3.8-flash`) | `lib/ai.py` |
| B | Speech-to-text (voice → text) | Gemini Transcribe (`gemini-3.5-transcribe`) | `lib/voice.py` |

Flow:

```
Telegram update → /api/webhook
  ├── text  ─────────────────────────────► Slot A
  └── voice → getFile → Slot B → transcript → Slot A
                                                 └── structured JSON
                                                     {tasks:[{title,time,priority,notes?}]}
                                                 └── confirmation (Save/Edit/Cancel)
```

### 6.2 Free-tier verification (checked 2026-10-19)

Source: https://ai.google.dev/gemini-api/docs/pricing (Free Tier column = "Free of charge")

- **Slot A**: Gemini 3.8 Flash / 3.6 Flash / Flash-Lite — free tier input+output, no credit card.
- **Slot B**: Gemini 3.5 Transcribe — free tier input (audio) + output (text).
- Free-tier limits (~10–15 RPM, ~1,000+ RPD, ~1.5M tokens/day) far exceed a 2-user workload.
- Caveats: Pro models are not on the free tier; free-tier content may be used to improve Google
  products; limits change over time — verify live numbers in AI Studio → Rate limits.

### 6.3 Config & flags

Secrets are env vars only: `GEMINI_API_KEY`.

Non-secret tunables default to the committed `config.defaults.json`:

```json
{
  "AI_MODEL_TEXT": "gemini-3.8-flash",
  "AI_MODEL_TRANSCRIBE": "gemini-3.5-transcribe",
  "USE_AI": false,
  "VOICE_QUEUE_MAX": 5,
  "VOICE_DRAIN_MAX": 3,
  "VOICE_RETRY_TTL_HOURS": 48,
  "UPCOMING_DAYS": 30
}
```

Precedence: env var > `config.defaults.json` > built-in default. `/api/debug` reports the
effective values plus `config_file_loaded`.

Fallback: any AI failure/timeout/invalid JSON → V1 rule parser. `USE_AI=false` preserves the
$0 rule-based behavior exactly.

### 6.4 Voice flow

1. Webhook detects `message.voice` (DM primary; group allowed).
2. Download via Bot API `getFile` (cap: 20 MB; voice notes are 0.1–2 MB).
3. Transcribe (Slot B) → text. Audio is discarded; nothing is stored on Vercel.
4. Transcript → Slot A → structured tasks.
5. Confirmation preview (existing Save/Edit/Cancel flow) shows the transcript for correction.

### 6.5 Slot B rate-limit handling & voice retry queue

On 429 (after one quick in-request retry with ~1–2 s backoff):

1. **Enqueue the voice**: one `conversation_state` row per pending voice
   (`state = {"kind":"pending_voice","file_id":…,"message_id":…,"duration":…,"status":"queued"}`,
   `expires_at = now + 48h`). One row per recording preserves order; no schema change needed.
2. **Reply once** with a Retry button, then **edit that same message** for subsequent recordings
   (avoids error spam): `"Transcription is busy. Recordings saved: {n}. Tap Retry or send /retry."`
3. **Retry triggers**:
   - `/retry` or the inline button → drain the user's queue oldest → newest.
   - `/retry` sent as a reply to a message containing a voice → prefer that `reply_to_message.voice.file_id`.
4. **Drain**: transcribe → Slot A → confirmation labeled `Recording {i}/{n}`; delete the row on success.
5. **Partial success**: stop on 429, keep the remainder queued, edit status:
   `"Transcribed {ok} of {n}. Tap Retry again in a minute."`
6. **Guards**:
   - Queue cap 5 → `"Too many recordings queued ({n}). Please wait before sending more."`
   - Drain cap 3 per request (stays within the serverless function timeout); the rest waits for the next retry.
   - Idempotency: mark rows `processing` at the start of a drain so a double-tap cannot double-parse.
   - Expired rows are removed by the existing cron state cleanup.

Decisions: **queue (not most-recent-only), cap 5, English copy in V2.** Vietnamese retry/status
copy is deferred to V3. Copy lives in `lib/messages.py` (see §3).

### 6.6 Date detection (v2.1)

Text and voice input may name a day; the task is then stored **for that date**
(`daily_tasks.for_date`, which already exists in V1 — no migration, no regex in the DB).

**Slot A (Gemini) — full set.** `parse_tasks_ai(text, today_iso, tz_name)` asks for a
nullable `date` field (`YYYY-MM-DD`) and resolves it against the local date:

| Wording | Resolves to |
|---|---|
| `hôm nay` / `today` / `tonight` | today |
| `ngày mai` / `mai` / `tomorrow` | +1 day |
| `ngày mốt` / `mốt` / `day after tomorrow` | +2 days |
| `thứ 2`..`chủ nhật` / `Monday`..`Sunday` | next occurrence (today counts if it matches) |
| `cuối tuần` / `weekend` | the coming Saturday |
| `tuần sau` / `next week` | the same weekday next week |
| `20/10`, `ngày 20 tháng 10`, `20 Oct`, `2026-10-20` | that date (day/month order) |

Validation (`lib/ai.py::_clean_date`) accepts only ISO inside `[today, today + 365]`.
Anything else — malformed or already past — is dropped and flagged as
`task["date_rejected"]`; the handler then uses the default date (tomorrow) and appends
*"That date is already in the past, so I saved it for {when} instead."*

**Local-date contract.** `today_iso` is the *group-local* date (`GROUP_TIMEZONE`), never
`datetime.now()`. Vercel runs UTC, so between 00:00 and 07:00 GMT+7 the UTC date is still
yesterday and "today" would silently resolve one day early.

**Rule parser (fallback) — deliberately narrow.** `lib/parser.py` understands only
today / tomorrow / day-after-tomorrow / weekend→Saturday. Explicit dates, weekdays and
`tuần sau` are AI-only. Two ordering details matter: date extraction runs **before** time
extraction and consumes the matched phrase, and date-ish segments skip the bare-hour rule —
otherwise `họp ngày 20 tháng 10` is read as `10:00` and `ngày 20` as `20:00`.

**Confirmation & listing.** Each task carries its own date in the confirmation state, so a
Save pressed later still lands on the right day. A single date renders
`Save for tomorrow (Tue 20 Oct)?`; several render grouped by date with
`Save these N tasks?`. `/list` shows today-forward tasks grouped by date
(`UPCOMING_DAYS`, default 30) with short ids for `/remove`.

**Overdue.** There is no done/cancelled flow yet, so overdue is *derived*, not stored:
`for_date < today and not done`. `/list` is today-forward and the digest filters
`for_date = today`, so overdue tasks appear in neither; the derivation is groundwork for the
done/snooze flow in §7 and adds no schema.

**Calendar readiness (v3).** `for_date` + `time_of_day` + `GROUP_TIMEZONE` map directly onto
Google Calendar `events.insert` `start.dateTime`/`end.dateTime`; `daily_tasks.google_event_id`
is the only column the v3 integration adds.

**Known trade-offs.**

- Slot A failure (429 / timeout / invalid JSON) falls back **silently** to the rule parser,
  which knows only the four relative phrases — so an explicit date in a fallback message
  lands on tomorrow. Intentional: the rule path stays small and predictable.
- Past dates are *reported*, not rolled forward, so the user sees exactly what happened.
- Ambiguous numeric dates are day/month (Vietnam style).
- Vague wording (`tuần sau`, `cuối tuần`) is resolved by the model, so it is best-effort
  rather than exact.

### 6.7 Quick date move (v2.1)

The confirmation message carries a second button row so a task can be pushed to
today/tomorrow without retyping it.

**When the buttons appear.** At least one task must be today or tomorrow — a batch of
explicit far-future dates was typed deliberately, so it gets neither button. Then:

| Batch dates | Move to today | Move to tomorrow |
|---|---|---|
| all today | — | ✅ |
| all tomorrow | ✅ | — |
| all ≥ today+2 | — | — |
| today + tomorrow | ✅ | ✅ |
| today + 20/12 | ✅ | ✅ |
| tomorrow + 20/12 | ✅ | — |

Rule: show **Move to today** if any task is later than today; show **Move to tomorrow**
if any task is today.

**Single date → one tap.** `messages.all_same_date(tasks)` → every task is re-dated and
the batch is saved immediately (`Moved 2 tasks to tomorrow (Tue 20 Oct).`).

**Mixed dates → pick which ones.** The tap stores a pointer and edits the message into a
picker (`move_pending:<user_id>` in the existing `settings` table — no schema change,
one pending move per user). The picker renders the task block with the *same*
`render_tasks(numbered=True)` used by the confirmation, so the numbers still match the
message the user is reading. Tasks are **not** filtered: a `20/12` task in the batch can
be pulled forward like any other, and a selected task is re-dated regardless of its
original date.

The reply is parsed by `parser.parse_selection()` (`1,2,4` / `1 2 4` / `1-3` / `all` /
`tất cả` / `cancel`) and is intercepted before the free-text task path. Replying with the
numbers **is** the confirmation: the selected tasks are re-dated and the whole batch —
edited and untouched alike — is saved. `cancel` (or the ❌ button) restores the original
confirmation via `edit_message_text`, nothing saved. An unparseable reply re-asks and
keeps waiting.

**Where it works.** The chat that was confirmed; in a group only when replying to the
bot's prompt (mirrors the group-voice rule). A pointer whose state has expired (the usual
15-minute window) is dropped and the text falls through as a normal message — deliberately
silent, no notice.

**Cost of the feature:** no migration, no new dependency, no env var, no cron change.
Callback payloads stay within Telegram's 64-byte limit (`move:` + uuid + target ≈ 50).

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
6. Voice retry queue reuses `conversation_state` (no migration needed).

## 11. Cost estimate V2 (2–10 users)

- Supabase free: still $0 at this scale.
- Vercel Hobby: $0; if cron frequency needs exceed limits, move scheduler to GitHub Actions (free) or a $5 VPS.
- AI parsing (Gemini Flash free tier): $0 under free limits; if exceeded, pennies/month at this scale.
- Voice transcription (Gemini Transcribe free tier): $0 under free limits.
- Total target: **$0–5/month**.

## 12. Open items for V2

- Voice privacy/storage policy (audio is discarded after transcription; free-tier content may be used to improve Google products).
- Monitor Gemini free-tier limits (verify live numbers in AI Studio before enabling `USE_AI`).
- Snooze UX and limits.
- Whether to store task history indefinitely or rotate.
- Self-serve user onboarding and admin approval.
- Whether to add a minimal web admin UI.

## 13. Not in V2 (deferred)

- Vietnamese UI messages and Vietnamese-language parsing (→ v3).
- Native mobile app.
- Full NLP sentiment/personality.
- Calendar integrations (Google/Apple).
- Payments/billing.
- Multi-region data residency.
