# Product Plan

## Overview

A Telegram reminder agent for personal use by a small, fixed group of 2 users (admin + partner). It collects default and daily tasks, then posts a single public digest to a shared group chat each morning. V1 is minimal, rule-based, and $0-cost on serverless. V2 adds intelligence and convenience.

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

## V2 candidates

- AI natural-language parser (Groq free tier) behind a flag.
- Voice input via Whisper transcription.
- Done/snooze tracking with inline buttons.
- DM mirror of the digest (opt-in).
- Per-user timezones and smarter scheduling.
- Multi-turn clarification conversation state.
- Task history, completion stats, personalization.
- Recurrence editing and exceptions (skip today, defer).
- Multi-group / multi-user scaling.
- Admin dashboard / web UI.
- Observability, tests, CI/CD.
- Multi-language.

## Milestones

1. V1 end-to-end: webhook, commands, parser, digest, cron, allowlists.
2. V1 hardening: idempotency, retries, cold-start handling, docs.
3. V2 intelligence: AI parser + confirmation improvements.
4. V2 convenience: voice + done/snooze + DM mirror.
5. V2 scale: multi-user/group, per-user tz, observability.
