"""User-facing copy for the bot.

English copy in v2. Vietnamese localization is deferred to v3, so keep all
wording here (and out of handlers) to make that switch a single-file change.
"""

BOT_NAME = "Minitu"

# ---- common ----
NOT_AUTHORIZED = "Not authorized."
ADMIN_ONLY = "Admin only."
UNKNOWN_COMMAND = "Unknown command. /help"
USER_NOT_AUTHORIZED_GROUP = "You aren't authorized to use this bot."
TASKS_AFTER_MENTION = "Send tasks after mentioning me, e.g. @bot tomorrow gym 6pm; report"


def group_not_allowed(chat_id):
    return (
        f"This group isn't allow-listed (ID: {chat_id}). "
        "Ask admin to update ALLOWED_GROUP_IDS in Vercel, then redeploy."
    )


GROUP_NOT_ALLOWED = "This group is not allowed."
USAGE_JOIN_DM = "Run /join inside the group chat."


def linked_to_group(chat_id):
    return f"Linked to group {chat_id}."


def registered(role, help_body):
    return f"Registered. {role}\n\n{help_body}"


def settings_text(group_timezone, allowed_users, allowed_groups, use_ai, ai_on, voice_on):
    return (
        "Settings (v2):\n"
        f"GROUP_TIMEZONE={group_timezone}\n"
        f"ALLOWED_USER_IDS={allowed_users}\n"
        f"ALLOWED_GROUP_IDS={allowed_groups}\n"
        f"USE_AI={use_ai} (AI parsing {'on' if ai_on else 'off'})\n"
        f"VOICE={'on' if voice_on else 'off'}\n"
        "Digest cron: 0 23 * * * UTC (=6AM GMT+7)\n"
    )


# ---- help ----
HELP_HEADER = "Task Reminder Bot (v2)"
HELP_BODY = (
    "Commands:\n"
    "/start - register\n"
    "/join - link this group (run in group)\n"
    "/add \"title\" HH:MM - add personal default reminder\n"
    "/default list|add|remove - manage your defaults\n"
    "/default shared list|add|remove - manage shared reminders (admin)\n"
    "/tomorrow <tasks> - set tomorrow's tasks (semicolon/comma/newline separated, time optional)\n"
    "/today - show today; /today <tasks> - set today's tasks\n"
    "/list - show your defaults and tasks\n"
    "/remove <id> - remove a reminder/task\n"
    "/retry - retry a voice note that couldn't be transcribed\n"
    "/settings - admin info\n"
    "/help - this message\n\n"
    "Free text in DM is treated as tomorrow's task input.\n"
    "Send a voice note in DM to add tasks by voice."
)


def help_text():
    return f"{HELP_HEADER}\n\n{HELP_BODY}"


# ---- task confirmation ----
COULD_NOT_PARSE = "Couldn't parse any tasks. Example:\nfinish report; gym 18:00; call mom"
CONFIRM_PROMPT = "I understood:\n{tasks}\n\nSave for {when}?"
TRANSCRIPT_PREFIX = "📝 Transcript: {transcript}"


def confirm_prompt(tasks_text, when, transcript=None, label=None):
    parts = []
    if label:
        parts.append(label)
    if transcript:
        parts.append(TRANSCRIPT_PREFIX.format(transcript=transcript))
    parts.append(CONFIRM_PROMPT.format(tasks=tasks_text, when=when))
    return "\n\n".join(parts)


def confirm_markup(state_id):
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Save", "callback_data": f"confirm:{state_id}"},
                {"text": "✏️ Edit", "callback_data": f"edit:{state_id}"},
                {"text": "❌ Cancel", "callback_data": f"cancel:{state_id}"},
            ]
        ]
    }


# ---- voice / Slot B rate limiting ----
VOICE_DISABLED = "Voice input isn't enabled on this bot (missing GEMINI_API_KEY)."
TRANSCRIBE_FAILED = "Couldn't transcribe that recording. Please try again."
TRANSCRIBE_EMPTY = "Couldn't hear any tasks in that recording. Please try again."
TRANSCRIBE_NONE_PENDING = "Nothing to retry."
TRANSCRIBE_QUEUE_FULL = "Too many recordings queued ({n}). Please wait before sending more."
TRANSCRIBE_BUSY = "Transcription is busy. Recordings saved: {n}. Tap Retry or send /retry."
TRANSCRIBE_PARTIAL = "Transcribed {ok} of {n}. Tap Retry again in a minute."
RETRY_BUTTON = "🔁 Retry"
RECORDING_LABEL = "Recording {i}/{n}"


def retry_markup():
    return {"inline_keyboard": [[{"text": RETRY_BUTTON, "callback_data": "retry:pending"}]]}
