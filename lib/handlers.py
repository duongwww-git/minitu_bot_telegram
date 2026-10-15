import re
import shlex
from datetime import date, datetime, timedelta

from zoneinfo import ZoneInfo

from lib import config, tg, repo, parser


def _tz():
    return ZoneInfo(config.GROUP_TIMEZONE)


def _today():
    return datetime.now(_tz()).date()


def _tomorrow():
    return _today() + timedelta(days=1)


def parse_command(text):
    text = (text or "").strip()
    if not text.startswith("/"):
        return None, ""
    parts = text.split(" ", 1)
    cmd = parts[0].split("@")[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""
    return cmd, args


def _auth_user(tg_user):
    tg_id = tg_user["id"]
    if not config.is_allowed_user(tg_id):
        return None
    username = tg_user.get("username")
    display = (tg_user.get("first_name") or "") + ((" " + tg_user.get("last_name")) if tg_user.get("last_name") else "")
    display = display.strip() or username
    return repo.upsert_user(tg_id, username, display)


def _is_admin(user):
    return bool(user and user.get("is_admin"))


def _primary_group_id(user_id):
    return repo.get_primary_group_id(user_id)


def _split_title_time(s):
    s = (s or "").strip()
    try:
        toks = shlex.split(s)
    except ValueError:
        toks = s.split()
    if not toks:
        return "", None
    last = toks[-1]
    if re.match(r"^\d{1,2}(:\d{2})?(am|pm)?$", last, re.I):
        title = " ".join(toks[:-1]).strip().strip("\"'")
        return title, last
    return " ".join(toks).strip().strip("\"'"), None


def _norm_time(tok):
    if not tok:
        return None
    # reuse parser time regex by treating "title 09:00"
    p = parser.parse_tasks("x " + tok)
    # extract time from the single dummy task if present
    t = parser.parse_tasks(tok)
    if t and t[0].get("time"):
        return t[0].get("time")
    # fallback
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?(am|pm)?$", tok, re.I)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    ampm = (m.group(3) or "").lower()
    if ampm == "am" and hour == 12:
        hour = 0
    elif ampm == "pm" and hour != 12:
        hour += 12
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def _help_text():
    return (
        "Task Reminder Bot (v1)\n\n"
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
        "/settings - admin info\n"
        "/help - this message\n\n"
        "Free text in DM is treated as tomorrow's task input."
    )


def _send(chat_id, text, markup=None):
    for chunk in tg.split_text(text):
        tg.send_message(chat_id, chunk, reply_markup=markup)
        markup = None  # only first chunk gets buttons


def start_task_input(user, chat_id, text, target_date, group_id):
    tasks = parser.parse_tasks(text)
    if not tasks:
        tg.send_message(
            chat_id,
            "Couldn't parse any tasks. Example:\nfinish report; gym 18:00; call mom",
        )
        return
    state = repo.create_state(
        user["id"],
        chat_id,
        {"action": "confirm_tasks", "tasks": tasks, "target_date": target_date.isoformat(), "group_id": group_id},
    )
    if not state:
        tg.send_message(chat_id, "Failed to create confirmation state. Try again.")
        return
    when = "today" if target_date == _today() else "tomorrow"
    body = "I understood:\n" + parser.format_tasks(tasks) + f"\n\nSave for {when}?"
    markup = {
        "inline_keyboard": [
            [
                {"text": "✅ Save", "callback_data": f"confirm:{state['id']}"},
                {"text": "✏️ Edit", "callback_data": f"edit:{state['id']}"},
                {"text": "❌ Cancel", "callback_data": f"cancel:{state['id']}"},
            ]
        ]
    }
    tg.send_message(chat_id, body, reply_markup=markup)


def _handle_remove(user, id_str, chat_id, group_id=None):
    id_str = (id_str or "").strip()
    if not id_str:
        tg.send_message(chat_id, "Usage: /remove <id>")
        return
    # try reminder
    r = repo.get_reminder(id_str)
    if r:
        # permission
        if r.get("user_id") is not None and r["user_id"] != user["id"] and not _is_admin(user):
            tg.send_message(chat_id, "Not allowed.")
            return
        if r.get("user_id") is None and not _is_admin(user):
            tg.send_message(chat_id, "Only admin can remove shared reminders.")
            return
        repo.remove_reminder(id_str)
        tg.send_message(chat_id, "Removed reminder.")
        return
    # daily task
    tasks = repo.list_daily_tasks(user_id=user["id"])
    match = [t for t in tasks if str(t["id"]) == id_str or str(t["id"]).startswith(id_str)]
    if match:
        repo.remove_daily_task(match[0]["id"])
        tg.send_message(chat_id, "Removed task.")
        return
    # admin can remove any daily task
    if _is_admin(user):
        # fetch by exact id best-effort (not in helper); try direct from db? skip
        pass
    tg.send_message(chat_id, "Not found. Use /list for IDs.")


def handle_command(cmd, args, user, chat_id, is_group=False, group_id=None):
    admin = _is_admin(user)

    if cmd == "/start":
        if is_group and group_id:
            g = repo.ensure_group(group_id, None)
            repo.link_membership(user["id"], g["id"])
        elif len(config.ALLOWED_GROUP_IDS) == 1:
            g = repo.ensure_group(config.ALLOWED_GROUP_IDS[0], None)
            repo.link_membership(user["id"], g["id"])
        tg.send_message(chat_id, "Registered. " + ("Admin." if admin else "User.") + "\n\n" + _help_text())
        return

    if cmd == "/help":
        tg.send_message(chat_id, _help_text())
        return

    if cmd == "/join":
        if not is_group:
            tg.send_message(chat_id, "Run /join inside the group chat.")
            return
        if not config.is_allowed_group(group_id):
            tg.send_message(chat_id, "This group is not allowed.")
            return
        g = repo.ensure_group(group_id, None)
        repo.link_membership(user["id"], g["id"])
        tg.send_message(chat_id, "Linked to group.")
        return

    if cmd in ("/add",):
        title, time_tok = _split_title_time(args)
        if not title:
            tg.send_message(chat_id, "Usage: /add \"title\" HH:MM")
            return
        time_val = _norm_time(time_tok) if time_tok else None
        gid = group_id if is_group else _primary_group_id(user["id"])
        r = repo.add_reminder(user_id=user["id"], group_id=None, title=title, time_of_day=time_val)
        tg.send_message(chat_id, f"Added personal reminder: {title}" + (f" @ {time_val}" if time_val else ""))
        return

    if cmd == "/default":
        tokens = []
        try:
            tokens = shlex.split(args or "")
        except ValueError:
            tokens = (args or "").split()
        sub = (tokens[0].lower() if tokens else "list")
        rest = " ".join(tokens[1:]).strip()

        if sub == "list":
            prefs = repo.list_reminders(user_id=user["id"])
            if not prefs:
                tg.send_message(chat_id, "No personal default reminders.")
                return
            msg = "Your default reminders:\n"
            for r in prefs:
                t = str(r.get("time_of_day"))[:5] if r.get("time_of_day") else "anytime"
                msg += f"- {str(r['id'])[:8]} | {t} {r['title']}\n"
            _send(chat_id, msg)
            return

        if sub == "add":
            title, time_tok = _split_title_time(rest)
            if not title:
                tg.send_message(chat_id, "Usage: /default add \"title\" HH:MM")
                return
            time_val = _norm_time(time_tok) if time_tok else None
            repo.add_reminder(user_id=user["id"], group_id=None, title=title, time_of_day=time_val)
            tg.send_message(chat_id, f"Added default reminder: {title}" + (f" @ {time_val}" if time_val else ""))
            return

        if sub == "remove":
            _handle_remove(user, rest, chat_id)
            return

        if sub == "shared":
            if not admin:
                tg.send_message(chat_id, "Admin only.")
                return
            shared_sub = (tokens[1].lower() if len(tokens) > 1 else "list")
            shared_rest = " ".join(tokens[2:]).strip()
            gid = group_id
            if gid is None:
                # fallback first allowed group
                allowed = config.ALLOWED_GROUP_IDS
                if allowed:
                    g = repo.ensure_group(allowed[0], None)
                    gid = g["id"]
            if shared_sub == "list":
                shared = repo.list_reminders(shared=True, group_id=gid)
                if not shared:
                    tg.send_message(chat_id, "No shared reminders.")
                    return
                msg = "Shared reminders:\n"
                for r in shared:
                    t = str(r.get("time_of_day"))[:5] if r.get("time_of_day") else "anytime"
                    msg += f"- {str(r['id'])[:8]} | {t} {r['title']}\n"
                _send(chat_id, msg)
                return
            if shared_sub == "add":
                title, time_tok = _split_title_time(shared_rest)
                if not title or gid is None:
                    tg.send_message(chat_id, "Usage: /default shared add \"title\" HH:MM (in group or admin)")
                    return
                time_val = _norm_time(time_tok) if time_tok else None
                repo.add_reminder(user_id=None, group_id=gid, title=title, time_of_day=time_val)
                tg.send_message(chat_id, f"Added shared reminder: {title}" + (f" @ {time_val}" if time_val else ""))
                return
            if shared_sub == "remove":
                _handle_remove(user, shared_rest, chat_id, group_id=gid)
                return
            tg.send_message(chat_id, "Usage: /default shared list|add|remove ...")
            return

        tg.send_message(chat_id, "Usage: /default list|add|remove or /default shared ...")
        return

    if cmd == "/tomorrow":
        if args:
            gid = group_id if is_group else _primary_group_id(user["id"])
            start_task_input(user, chat_id, args, _tomorrow(), gid)
        else:
            tg.send_message(chat_id, "Usage: /tomorrow gym 18:00; report")
        return

    if cmd == "/today":
        if args:
            gid = group_id if is_group else _primary_group_id(user["id"])
            start_task_input(user, chat_id, args, _today(), gid)
        else:
            gid = group_id
            uid = user["id"]
            tasks = repo.list_daily_tasks(user_id=uid, group_id=gid, for_date=_today().isoformat())
            if not tasks:
                tg.send_message(chat_id, "No tasks for today.")
                return
            msg = "Today's tasks:\n"
            for t in tasks:
                tt = str(t.get("time_of_day"))[:5] if t.get("time_of_day") else "anytime"
                msg += f"- {str(t['id'])[:8]} | {tt} {t['title']}\n"
            tg.send_message(chat_id, msg)
        return

    if cmd == "/list":
        uid = user["id"]
        prefs = repo.list_reminders(user_id=uid)
        today = _today().isoformat()
        tasks = repo.list_daily_tasks(user_id=uid, for_date=today)
        # if admin, also show shared? include shared for primary group
        gid = _primary_group_id(uid)
        shared = repo.list_reminders(shared=True, group_id=gid) if gid else []
        msg = "Your default reminders:\n"
        if prefs:
            for r in prefs:
                t = str(r.get("time_of_day"))[:5] if r.get("time_of_day") else "anytime"
                msg += f"- {str(r['id'])[:8]} | {t} {r['title']}\n"
        else:
            msg += "(none)\n"
        if shared:
            msg += "\nShared reminders:\n"
            for r in shared:
                t = str(r.get("time_of_day"))[:5] if r.get("time_of_day") else "anytime"
                msg += f"- {str(r['id'])[:8]} | {t} {r['title']}\n"
        msg += f"\nToday's tasks ({today}):\n"
        if tasks:
            for t in tasks:
                tt = str(t.get("time_of_day"))[:5] if t.get("time_of_day") else "anytime"
                msg += f"- {str(t['id'])[:8]} | {tt} {t['title']}\n"
        else:
            msg += "(none)\n"
        _send(chat_id, msg)
        return

    if cmd == "/remove":
        _handle_remove(user, args, chat_id, group_id=group_id)
        return

    if cmd == "/settings":
        if not admin:
            tg.send_message(chat_id, "Admin only.")
            return
        msg = (
            "Settings (v1 fixed):\n"
            f"GROUP_TIMEZONE={config.GROUP_TIMEZONE}\n"
            f"ALLOWED_USER_IDS={config.ALLOWED_USER_IDS}\n"
            f"ALLOWED_GROUP_IDS={config.ALLOWED_GROUP_IDS}\n"
            "Digest cron: 0 23 * * * UTC (=6AM GMT+7)\n"
        )
        tg.send_message(chat_id, msg)
        return

    tg.send_message(chat_id, "Unknown command. /help")


def handle_private_message(chat_id, tg_user, text):
    user = _auth_user(tg_user)
    if not user:
        tg.send_message(chat_id, "Not authorized.")
        return
    cmd, args = parse_command(text)
    if cmd:
        handle_command(cmd, args, user, chat_id, is_group=False, group_id=None)
        return
    # free text -> tomorrow input
    gid = _primary_group_id(user["id"])
    start_task_input(user, chat_id, text, _tomorrow(), gid)


def _bot_mentioned(text):
    bot_un = tg.get_bot_username()
    if not bot_un:
        return False, text
    mention = f"@{bot_un}".lower()
    low = text.lower()
    if mention in low:
        cleaned = text.replace(f"@{bot_un}", "").replace(f"@{bot_un.lower()}", "")
        # case-insensitive removal approximation
        cleaned = low.replace(mention, "") if False else text
        # do a simple case-insensitive removal
        import re as _re
        cleaned = _re.sub(r"@" + re.escape(bot_un), "", text, flags=re.I)
        return True, cleaned.strip()
    return False, text


def handle_group_message(chat_id, tg_user, text, msg):
    if not config.is_allowed_group(chat_id):
        tg.send_message(
            chat_id,
            f"This group isn't allow-listed (ID: {chat_id}). Ask admin to update ALLOWED_GROUP_IDS in Vercel, then redeploy.",
        )
        return
    if not config.is_allowed_user(tg_user["id"]):
        tg.send_message(chat_id, "You aren't authorized to use this bot.")
        return
    user = _auth_user(tg_user)
    if not user:
        return
    group = repo.ensure_group(chat_id, msg.get("chat", {}).get("title"))
    group_id = group["id"]
    repo.link_membership(user["id"], group_id)

    cmd, args = parse_command(text)
    if cmd:
        handle_command(cmd, args, user, chat_id, is_group=True, group_id=group_id)
        return

    # process free text only if bot mentioned or reply to bot
    reply_to = (msg.get("reply_to_message") or {}).get("from") or {}
    reply_to_bot = bool(reply_to.get("is_bot"))
    mentioned, cleaned = _bot_mentioned(text)
    if not (mentioned or reply_to_bot):
        return  # ignore group chatter

    text_to_parse = cleaned if cleaned else text
    if not text_to_parse.strip():
        tg.send_message(chat_id, "Send tasks after mentioning me, e.g. @bot tomorrow gym 6pm; report")
        return
    start_task_input(user, chat_id, text_to_parse, _tomorrow(), group_id)


def handle_callback(callback_query):
    cq_id = callback_query["id"]
    from_user = callback_query["from"]
    tg_user_id = from_user["id"]
    if not config.is_allowed_user(tg_user_id):
        tg.answer_callback_query(cq_id, "Not authorized.", show_alert=True)
        return
    user = _auth_user(from_user)
    if not user:
        tg.answer_callback_query(cq_id, "Not authorized.", show_alert=True)
        return
    data = callback_query.get("data") or ""
    msg = callback_query.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    if ":" not in data:
        tg.answer_callback_query(cq_id)
        return
    action, state_id = data.split(":", 1)
    state = repo.get_state(state_id)
    if not state or str(state.get("user_id")) != str(user["id"]):
        tg.answer_callback_query(cq_id, "Expired or invalid.", show_alert=True)
        return
    st = state.get("state") or {}
    tasks = st.get("tasks") or []
    target_date_str = st.get("target_date")
    group_id = st.get("group_id")

    if action == "confirm":
        try:
            td = target_date_str
            inserted = 0
            for t in tasks:
                repo.add_daily_task(user["id"], group_id, td, t["title"], t.get("time"))
                inserted += 1
            repo.delete_state(state_id)
            tg.answer_callback_query(cq_id, "Saved.")
            tg.send_message(chat_id, f"Saved {inserted} task(s) for {td}.")
        except Exception as e:
            tg.answer_callback_query(cq_id, "Failed to save.", show_alert=True)
            tg.send_message(chat_id, f"Error saving tasks: {e}")
        return

    if action == "cancel":
        repo.delete_state(state_id)
        tg.answer_callback_query(cq_id, "Cancelled.")
        if chat_id:
            tg.send_message(chat_id, "Cancelled.")
        return

    if action == "edit":
        repo.delete_state(state_id)
        tg.answer_callback_query(cq_id, "Resend corrected list.")
        if chat_id:
            tg.send_message(chat_id, "Send the corrected task list, or /tomorrow ... again.")
        return

    tg.answer_callback_query(cq_id)