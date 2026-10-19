"""User-facing copy for the bot.

English copy in v2. Vietnamese localization is deferred to v3, so keep all
wording here (and out of handlers) to make that switch a single-file change.
"""

from datetime import date

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
    "Free text in DM is treated as tomorrow's task input unless you name a day:\n"
    "\"today gym 18:00\", \"mai họp 14:00\", \"ngày 20 tháng 10 mua quà\".\n"
    "On the confirmation, tap 📅 to push the tasks to today/tomorrow (with mixed\n"
    "dates you pick which ones by number), or ✅ Save to keep the dates as shown.\n"
    "Send a voice note in DM to add tasks by voice."
)


def help_text():
    return f"{HELP_HEADER}\n\n{HELP_BODY}"


# ---- dates (v2.1) ----

_WEEKDAYS_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS_SHORT = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _as_date(value):
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def short_date(d):
    """Tue 20 Oct"""
    return f"{_WEEKDAYS_SHORT[d.weekday()]} {d.day} {_MONTHS_SHORT[d.month - 1]}"


def format_date_label(iso, today=None):
    """Human label for a date: 'today (Tue 19 Oct)', 'tomorrow (…)' or 'Tue 20 Oct'."""
    d = _as_date(iso)
    if d is None:
        return str(iso or "")
    td = _as_date(today)
    if td is not None:
        delta = (d - td).days
        if delta == 0:
            return f"today ({short_date(d)})"
        if delta == 1:
            return f"tomorrow ({short_date(d)})"
        if delta == 2:
            return f"the day after tomorrow ({short_date(d)})"
    return short_date(d)


def task_line(task, show_id=False):
    time_val = task.get("time") or task.get("time_of_day")
    time_part = f" — {str(time_val)[:5]}" if time_val else " — (no time)"
    id_part = f"[{str(task['id'])[:8]}] " if show_id and task.get("id") else ""
    return f"{id_part}{task.get('title')}{time_part}"


def render_tasks(tasks, today=None, numbered=False, always_group=False, show_id=False):
    """Render tasks, grouping under a date header when dates vary (or always)."""
    dates = []
    for t in tasks:
        d = t.get("date") or ""
        if d not in dates:
            dates.append(d)
    grouped = always_group or len(dates) > 1

    def bullet(t):
        return f"  • {task_line(t, show_id=show_id)}"

    def numbered_line(i, t):
        return f"{i}. {task_line(t)}"

    if not grouped:
        if numbered:
            return "\n".join(numbered_line(i, t) for i, t in enumerate(tasks, 1))
        return "\n".join(bullet(t) for t in tasks)

    lines = []
    counter = 0
    for d in dates:
        lines.append(format_date_label(d, today) if d else "No date")
        group = [t for t in tasks if (t.get("date") or "") == d]
        if numbered:
            for t in group:
                counter += 1
                lines.append(numbered_line(counter, t))
        else:
            lines.extend(bullet(t) for t in group)
    return "\n".join(lines)


def all_same_date(tasks):
    return len({(t.get("date") or "") for t in tasks}) <= 1


# ---- task confirmation ----
COULD_NOT_PARSE = "Couldn't parse any tasks. Example:\nfinish report; gym 18:00; call mom"
CONFIRM_HEADER = "I understood:"
CONFIRM_SAVE_ONE = "Save for {when}?"
CONFIRM_SAVE_MANY = "Save these {n} tasks?"
DATE_IN_PAST = "That date is already in the past, so I saved it for {when} instead."
TRANSCRIPT_PREFIX = "📝 Transcript: {transcript}"


def confirm_prompt(tasks_text, when=None, count=0, transcript=None, label=None):
    parts = []
    if label:
        parts.append(label)
    if transcript:
        parts.append(TRANSCRIPT_PREFIX.format(transcript=transcript))
    parts.append(f"{CONFIRM_HEADER}\n{tasks_text}")
    if when:
        parts.append(CONFIRM_SAVE_ONE.format(when=when))
    else:
        parts.append(CONFIRM_SAVE_MANY.format(n=count))
    return "\n\n".join(parts)


def _n_tasks(n):
    return f"{n} task" if n == 1 else f"{n} tasks"


def saved_summary(per_date, today=None):
    """'Saved 3 tasks: 2 for tomorrow (Tue 20 Oct), 1 for Thu 22 Oct.'"""
    total = sum(per_date.values())
    if len(per_date) == 1:
        d = next(iter(per_date))
        return f"Saved {_n_tasks(total)} for {format_date_label(d, today)}."
    parts = ", ".join(
        f"{n} for {format_date_label(d, today)}" for d, n in sorted(per_date.items())
    )
    return f"Saved {_n_tasks(total)}: {parts}."


def confirm_markup(state_id, move_targets=None):
    rows = [
        [
            {"text": "✅ Save", "callback_data": f"confirm:{state_id}"},
            {"text": "✏️ Edit", "callback_data": f"edit:{state_id}"},
            {"text": "❌ Cancel", "callback_data": f"cancel:{state_id}"},
        ]
    ]
    move_row = [
        {
            "text": MOVE_TO_TODAY if target == "today" else MOVE_TO_TOMORROW,
            "callback_data": f"move:{state_id}:{target}",
        }
        for target in (move_targets or [])
    ]
    if move_row:
        rows.append(move_row)
    return {"inline_keyboard": rows}


# ---- v2.1: quick date move ----
MOVE_TO_TODAY = "📅 Move to today"
MOVE_TO_TOMORROW = "📅 Move to tomorrow"
MOVE_CANCEL_BUTTON = "❌ Cancel"
MOVE_PICK_HEADER = "Move which tasks to {when}?"
MOVE_PICK_HINT = "Reply with numbers (e.g. 1, 3), 'all', or 'cancel'."
MOVE_INVALID = "I didn't catch that. Reply with numbers like 1, 3, 'all', or 'cancel'."
MOVE_CANCELLED = "Kept the original dates."


def move_picker(tasks, target_iso, today=None):
    """The 'which tasks?' prompt.

    The task block is rendered with the same numbered renderer as the original
    confirmation, so the numbers the user saw still match. Tasks are not
    filtered: a far-future task can be pulled forward just like any other.
    """
    return (
        MOVE_PICK_HEADER.format(when=format_date_label(target_iso, today))
        + "\n"
        + render_tasks(tasks, today=today, numbered=True)
        + "\n\n"
        + MOVE_PICK_HINT
    )


def move_markup(state_id):
    return {
        "inline_keyboard": [
            [{"text": MOVE_CANCEL_BUTTON, "callback_data": f"cancel_move:{state_id}"}]
        ]
    }


def moved_saved_summary(moved, target_iso, per_date, today=None):
    """'Moved 2 tasks to tomorrow (Tue 20 Oct).' plus the per-date save summary."""
    when = format_date_label(target_iso, today)
    total = sum(per_date.values())
    if moved and moved == total:
        return f"Moved {_n_tasks(moved)} to {when}."
    if moved:
        return f"Moved {_n_tasks(moved)} to {when}. " + saved_summary(per_date, today)
    return saved_summary(per_date, today)


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
