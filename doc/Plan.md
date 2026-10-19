# Product Plan

## Overview

A Telegram reminder agent for personal use by a small, fixed group of 2 users (admin + partner). It collects default and daily tasks, then posts a single public digest to a shared group chat each morning. V1 is minimal, rule-based, and $0-cost on serverless. V2 adds intelligence and convenience. V3 adds Google Calendar two-way integration and Vietnamese localization. V4 adds an optional web GUI that extends — not replaces — the Telegram bot.

## V1 scope (minimal, rule-based, $0)

**Users**
- Exactly 2 allowed Telegram user IDs (admin + partner).
- 1 shared group chat.

**Inputs**
- Each user manages their own tasks primarily via DM to the bot.
- Rule-based free-text parser (split punctuation, time regex) with confirmation step.
- Commands: `/start`, `/join`, `/add`, `/default`, `/tomorrow`, `/today`, `/list`, `/help`, admin `/settings`.
- Shared group reminders (e.g. "Take out trash") managed by admin.

**Outputs**
- One public digest per day in the group chat at 6:00 AM GMT+7 (23:00 UTC).
- Digest lists each user's applicable defaults + daily tasks, plus shared tasks.
- No DM mirror in v1.

**Infrastructure**
- Vercel (Python) for webhook + cron.
- Supabase free Postgres.
- Vercel Cron (`0 23 * * *`).
- Telegram Bot API.

**Explicitly not in v1**
- No AI/LLM.
- No voice input.
- No done/snooze tracking.
- No multi-timezone per user (fixed UTC cron).
- No scaling beyond the 2 users / 1 group.

## V2 candidates (in scope)

- AI natural-language parser via Google Gemini Flash (free tier) behind a flag, with the V1 rule parser as fallback.
- Voice input: transcribe Telegram voice notes via Google Gemini Transcribe (free tier), with a retry queue when transcription is rate-limited (queue cap 5; English copy).
- English UI/parsing copy in v2 (Vietnamese localization deferred to v3).

## V2.1 scope (date detection)

- Free text and voice notes can name a day, and the task is saved for that date (`daily_tasks.for_date`; no schema change).
- Slot A resolves relative days (`hôm nay`, `mai`, `mốt`), weekdays (`thứ 2`..`chủ nhật`), `cuối tuần`/`tuần sau`, and explicit dates (`20/10`, `ngày 20 tháng 10`, `20 Oct`, ISO) — numeric dates are day/month (Vietnam style).
- Validation window `[today, today + 365]`; a past date falls back to the default (tomorrow) and the bot says so.
- Rule-parser fallback covers only today / tomorrow / day-after-tomorrow / weekend→Saturday; explicit dates and weekdays are AI-only, so the fallback stays predictable.
- `/list` shows today-forward tasks grouped by date (`UPCOMING_DAYS`, default 30); overdue is derived (`for_date < today and not done`) and appears in neither `/list` nor the digest.
- Quick date move: the confirmation offers **📅 Move to today / tomorrow** when at least one task is today or tomorrow. One shared date moves on the tap; mixed dates ask which tasks by number (`1, 3`, `1-3`, `all`) and the reply moves the subset and saves the whole batch. Far-future tasks can be pulled forward. No schema change (pointer in `settings`).
- Reliability: each Gemini call tries one model once and falls back through an ordered model list (`AI_MODEL_TEXT_FALLBACKS`, `AI_MODEL_TRANSCRIBE_FALLBACKS`) — no in-request retry, because the free tier allows 20 requests per model per day. A voice note that exhausts the chain on a 5xx joins the existing retry queue. `gemini-3.5-transcribe` returns its text under `audioTranscription.text`, which `_extract_text` now reads.
- No migration required; groundwork for the v3 Calendar integration (`google_event_id`).

## V3 scope (Google Calendar integration + Vietnamese localization)

Two-way sync between Minitu tasks and Google Calendar, limited to 2 users:

- **Minitu → Google Calendar**: when a task is created with a date/time + invitee (limit 2), create a Google Calendar event via the Calendar API (`events.insert`) with `start.dateTime`, `end.dateTime`, and up to 2 `attendees`. Store the returned `google_event_id` on the task row.
- **Google Calendar → Minitu**: when a Calendar event is created/updated (date/time changed), sync back into Supabase so the task reflects in the daily digest. Implemented via polling (`events.list` with `updatedMin`) via cron, or Google Calendar push webhooks; match by `google_event_id` and apply date/time updates.
- **Data model**: `users.google_refresh_token` (encrypted), `users.google_calendar_connected`; `daily_tasks`/`reminders.google_event_id`, `.google_synced_at`.
- **Conflict rule**: last-write-wins by `updated_at`; conflicting edits flagged for manual resolution.
- **Cost**: $0/month at 2-user scale (Google Calendar API free quota, OAuth2 testing mode with 2 users, no app verification needed).
- **Vietnamese localization**: Vietnamese UI messages and Vietnamese-language task parsing (extends v2's English-only copy), including the voice retry/status messages.

## V4 scope (Web GUI app — Telegram hybrid)

The web GUI is an **extension** of the Telegram bot, not a replacement. Telegram remains the notification channel; the web app provides richer task management.

**Core requirements**
1. Tasks stay the same in the backend — Supabase remains the single source of truth.
2. Users still get notifications through Telegram (existing digest + cron unchanged).
3. The daily digest (and other notifications) include deep links to the web app for GUI task management.
4. Users can add tasks from both the GUI and Telegram chat.
5. Tasks updated on the GUI reflect on the Telegram digest, and tasks updated on Telegram reflect on the GUI (natural two-way sync via shared Supabase rows).

**What to build**
- **Web frontend**: static site on Vercel Hobby (React/Vue/plain HTML+JS) — list tasks, add/edit/delete, view digest.
- **Auth bridge (Telegram → web)**: Telegram Login Widget (server-side hash verification → session cookie) or bot-issued magic link (`/web` command in DM returns a single-use signed URL).
- **Deep links in Telegram**: digest footer / per-task links like `https://<vercel-url>/tasks/<task-id>?token=<sig>`.
- **Web API routes**: new Vercel functions (`GET/POST/PATCH/DELETE /api/tasks`, `GET /api/digest`) reusing existing `lib/db.py`, `lib/parser.py`, `lib/digest.py`.

**Sync semantics**
- Both clients write to the same Supabase tables (`daily_tasks`, `reminders`).
- GUI edits made before the morning digest cut-off appear in that day's digest; edits after cut-off appear the next day.
- Telegram-added tasks appear in the GUI on next page load (no realtime required; optional Supabase Realtime later).

**Cost**: ~$0/month — Vercel Hobby (frontend + API), Supabase free, Telegram Bot API free. Optional custom domain ~$12/yr.

**Out of scope for V4**
- Native iOS app, native push (APNs), offline mode, App Store distribution (see analysis below).

## Future idea (not scheduled): native iOS app

Analysis saved for later exploration — build the V4 web GUI first, validate usage, then consider a native app.

**Why deferred**
- Requires Apple Developer Program ($99/year) and App Store review process.
- Significant frontend investment before we know how much the mobile web GUI is actually used.

**What would be required**
- **Apple Developer account**: $99/year (mandatory for build/sign/distribute).
- **Native frontend**: Swift/SwiftUI (iOS-only) or React Native/Flutter (shared code with web frontend). Full CRUD + task list + digest view.
- **Push notifications**: APNs setup (certs, provisioning) to replace or supplement Telegram notifications.
- **Deep links**: Universal Links so Telegram digest links open the iOS app at the right task.
- **Auth**: reuse Supabase auth, plus iOS keychain + Face ID / Touch ID integration.
- **Offline support**: local storage (SQLite/Core Data) + sync on reconnect.
- **App Store review**: ongoing process for updates.

**Backend impact**: low — the existing Vercel API + Supabase serve the iOS app unchanged; optionally add a small Vercel function as an APNs provider.

**Recommended migration path**
1. Ship V4 hybrid (Telegram + web GUI) and validate usage.
2. If mobile web is too clunky, build React Native / Flutter app sharing logic with web, calling the same Vercel API, adding APNs push.
3. Only go fully native (Swift) if iOS-specific features are needed.

## Future idea (not scheduled): homework management app (small extra-class)

A separate app built from the same architecture template as Minitu, scoped for managing homework in a small extra-class.

**Roles**
- **Teachers**: create/manage homework tasks, assign tasks to specific students, set deadlines, optionally attach a link to homework materials.
- **Students**: view only homework assigned to themselves; see deadlines and optional links; submit work; request a deadline extension (to be continued).
- **Parents**: linked to their children's profiles; view only homework assigned to their children; can submit homework on behalf of their child.

**Access control (row-level isolation)**
- Students see only their own homework — never other students'.
- Parents see only their own children's homework — never other children's.
- Teachers see all homework they created/manage.

**Core entities**
- `users` (role: teacher / parent / student)
- `student_parent_links` (parent_id ↔ child_id)
- `homework_tasks` (title, description, link, deadline, assigned_student_id, created_by_teacher_id, status)
- `submissions` (task_id, student_id, submitted_by, file/link, submitted_at)
- `deadline_extension_requests` (task_id, student_id, requested_new_deadline, status)

**Notifications**: Telegram bot digest (existing pattern) with deep links to the web GUI for viewing/submitting homework.

## Future idea (not scheduled): investment DCA recommendation app

A separate app built from the same architecture template, but different purpose: read market data and recommend a basic DCA plan.

**Function**
- Reads HNX/HOSE stock prices, crypto currency prices, and liquidity data.
- Based on user's chosen strategy (risk appetite + budget), recommends a basic DCA plan: how much to invest, on what interval, where to invest (which stock/crypto).

**Core entities**
- `users` (investor profile)
- `user_strategies` (risk appetite, budget, preferred assets)
- `market_data` (price snapshots for HNX/HOSE stocks + crypto)
- `dca_recommendations` (asset, amount, interval, next_investment_date, status)
- `investment_logs` (executed investments)

**Notifications**: Telegram bot or email reminders for scheduled DCA investments.

## Shared architecture template (for future apps)

Both future apps (homework + investment) share the same "How" (logic and design) but differ in "What" and "Where" — each gets its own Supabase Postgres DB and its own Vercel deployment.

| Layer | Shared design |
|---|---|
| **Frontend** | Web GUI (Vercel static site, React/Vue/plain HTML+JS), role-aware UI |
| **Backend** | Vercel serverless Python (FastAPI + Mangum), same `lib/` pattern as V1 |
| **Database** | Supabase Postgres — **one database per app**, fully isolated |
| **Auth / access** | Role-based access control (RBAC); user profiles with linked relationships |
| **Core pattern** | Users → roles → items (homework tasks or DCA recommendations) → deadlines/schedules → status → submissions/results |
| **Notifications** | Telegram bot as optional channel; digest-style messages with deep links to web GUI |
| **Deep links** | `https://<vercel-url>/items/<id>?token=<sig>` in Telegram messages |
| **Deployment** | Separate Vercel project per app; separate Supabase project per app |

**Divergence**

| | Homework App | Investment App |
|---|---|---|
| **What** | Task lifecycle: assign → view → submit → delay request | Data ingestion + DCA recommendation engine |
| **Where** | Vercel project A + Supabase project A (extra-class) | Vercel project B + Supabase project B (investment tool) |
| **Primary entities** | Homework tasks, submissions, parent-child links | Market data, strategies, DCA recommendations |
| **Notification trigger** | New homework assigned / deadline approaching | Scheduled DCA investment date / price alert |

**Implementation path (future, not scheduled)**
1. Ship V1–V4 first (Telegram bot, AI parser, voice, Vietnamese, Google Calendar, web GUI).
2. Extract the shared backend template (`lib/db.py`, `lib/parser.py`, auth, RBAC patterns) into a reusable starter.
3. Clone the template for Extension A (homework) — deploy separate Vercel + Supabase.
4. Clone the template for Extension B (investment) — deploy separate Vercel + Supabase; add market data ingestion jobs.

## Milestones

1. V1 end-to-end: webhook, commands, parser, digest, cron, allowlists.
2. V1 hardening: idempotency, retries, cold-start handling, docs.
3. V2 intelligence: AI parser (Gemini Flash) + confirmation improvements.
4. V2 convenience: voice input (Gemini Transcribe + retry queue) + English copy.
5. V3: Google Calendar two-way integration (Minitu ↔ Calendar, 2 users) + Vietnamese localization.
6. V4: Web GUI extension (Telegram auth bridge, task CRUD UI, digest deep links, two-way sync).
