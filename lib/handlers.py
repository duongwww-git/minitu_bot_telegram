import re
import shlex
from datetime import date, datetime, timedelta

from zoneinfo import ZoneInfo

from lib import ai, config, tg, repo, parser, voice
from lib import messages


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
    return messages.help_text()


def _send(chat_id, text, markup=None):
    for chunk in tg.split_text(text):
        tg.send_message(chat_id, chunk, reply_markup=markup)
        markup = None  # only first chunk gets buttons


def _parse_tasks(text):
    """AI first (Slot A, when enabled), else fall back to the v1 rule parser."""
    if config.AI_ENABLED:
        tasks = ai.parse_tasks_ai(text)
        if tasks:
            return tasks
    return parser.parse_tasks(text)


def start_task_input(user, chat_id, text, target_date, group_id, transcript=None, label=None):
    tasks = _parse_tasks(text)
    if not tasks:
        tg.send_message(chat_id, messages.COULD_NOT_PARSE)
        return
    state_payload = {
        "action": "confirm_tasks",
        "tasks": tasks,
        "target_date": target_date.isoformat(),
        "group_id": group_id,
    }
    if transcript:
        state_payload["transcript"] = transcript
    state = repo.create_state(user["id"], chat_id, state_payload)
    if not state:
        tg.send_message(chat_id, "Failed to create confirmation state. Try again.")
        return
    when = "today" if target_date == _today() else "tomorrow"
    body = messages.confirm_prompt(parser.format_tasks(tasks), when, transcript=transcript, label=label)
    tg.send_message(chat_id, body, reply_markup=messages.confirm_markup(state["id"]))


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
        if is_group and config.is_allowed_group(chat_id):
            g = repo.ensure_group(chat_id, None)
            repo.link_membership(user["id"], g["id"])
        elif len(config.ALLOWED_GROUP_IDS) == 1:
            g = repo.ensure_group(config.ALLOWED_GROUP_IDS[0], None)
            repo.link_membership(user["id"], g["id"])
        tg.send_message(chat_id, messages.registered("Admin." if admin else "User.", _help_text()))
        return

    if cmd == "/help":
        tg.send_message(chat_id, _help_text())
        return

    if cmd == "/join":
        if not is_group:
            tg.send_message(chat_id, messages.USAGE_JOIN_DM)
            return
        if not config.is_allowed_group(chat_id):
            tg.send_message(chat_id, messages.GROUP_NOT_ALLOWED)
            return
        g = repo.ensure_group(chat_id, None)
        repo.link_membership(user["id"], g["id"])
        tg.send_message(chat_id, messages.linked_to_group(chat_id))
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
        tg.send_message(
            chat_id,
            messages.settings_text(
                config.GROUP_TIMEZONE,
                config.ALLOWED_USER_IDS,
                config.ALLOWED_GROUP_IDS,
                config.USE_AI,
                config.AI_ENABLED,
                config.VOICE_ENABLED,
            ),
        )
        return

    tg.send_message(chat_id, "Unknown command. /help")


def handle_private_message(chat_id, tg_user, text, tg_msg=None):
    user = _auth_user(tg_user)
    if not user:
        tg.send_message(chat_id, messages.NOT_AUTHORIZED)
        return
    cmd, args = parse_command(text)
    if cmd:
        if cmd == "/retry":
            retry_voice(user, chat_id, tg_msg)
            return
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
        tg.send_message(chat_id, messages.group_not_allowed(chat_id))
        return
    if not config.is_allowed_user(tg_user["id"]):
        tg.send_message(chat_id, messages.USER_NOT_AUTHORIZED_GROUP)
        return
    user = _auth_user(tg_user)
    if not user:
        return
    group = repo.ensure_group(chat_id, msg.get("chat", {}).get("title"))
    group_id = group["id"]
    repo.link_membership(user["id"], group_id)

    cmd, args = parse_command(text)
    if cmd:
        if cmd == "/retry":
            retry_voice(user, chat_id, msg)
            return
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
        tg.send_message(chat_id, messages.TASKS_AFTER_MENTION)
        return
    start_task_input(user, chat_id, text_to_parse, _tomorrow(), group_id)


# -------- v2: voice input (Slot B) + retry queue --------


def _group_id_for_chat(user, chat_id):
    group = repo.get_group_by_tg(chat_id)
    if group:
        return group["id"]
    return _primary_group_id(user["id"])


def _voice_status_key(user_id):
    return f"voice_status:{user_id}"


def _voice_status_ref(user_id):
    raw = repo.get_setting(_voice_status_key(user_id))
    if not raw:
        return None
    try:
        chat_id, message_id = str(raw).split(":", 1)
        return int(chat_id), int(message_id)
    except (ValueError, AttributeError):
        return None


def _update_voice_status(user, chat_id, text):
    """Show/refresh the single retry status message (edit in place, no spam)."""
    ref = _voice_status_ref(user["id"])
    if ref and ref[0] == chat_id:
        try:
            tg.edit_message_text(ref[0], ref[1], text, reply_markup=messages.retry_markup())
            return
        except Exception:
            pass
    result = tg.send_message(chat_id, text, reply_markup=messages.retry_markup())
    if result and result.get("message_id"):
        repo.set_setting(_voice_status_key(user["id"]), f"{chat_id}:{result['message_id']}")


def _clear_voice_status(user, delete_message=False):
    ref = _voice_status_ref(user["id"])
    if ref and delete_message:
        tg.delete_message(ref[0], ref[1])
    repo.delete_setting(_voice_status_key(user["id"]))


def _enqueue_voice(user, chat_id, voice_msg):
    count = repo.count_pending_voices(user["id"], chat_id)
    if count >= config.VOICE_QUEUE_MAX:
        tg.send_message(chat_id, messages.TRANSCRIBE_QUEUE_FULL.format(n=count))
        return None
    return repo.enqueue_pending_voice(
        user["id"],
        chat_id,
        voice_msg.get("file_id"),
        message_id=voice_msg.get("message_id"),
        duration=voice_msg.get("duration"),
    )


def _extract_voice(msg):
    """Normalize a Telegram update message into the voice payload used below.

    app.py passes the whole message, so the audio fields live under msg["voice"]
    while the message context (id, reply-to, chat) is on the message itself.
    """
    v = msg.get("voice") or {}
    return {
        "file_id": v.get("file_id"),
        "duration": v.get("duration"),
        "mime_type": v.get("mime_type"),
        "message_id": msg.get("message_id"),
        "reply_to_message": msg.get("reply_to_message"),
        "chat": msg.get("chat"),
    }


def _handle_voice(user, chat_id, voice_msg, group_id=None, target_date=None):
    if not config.VOICE_ENABLED:
        tg.send_message(chat_id, messages.VOICE_DISABLED)
        return
    file_id = (voice_msg or {}).get("file_id")
    if not file_id:
        print("voice failed: missing file_id in voice payload")
        tg.send_message(chat_id, messages.TRANSCRIBE_FAILED)
        return
    target_date = target_date or _tomorrow()
    if group_id is None:
        group_id = _group_id_for_chat(user, chat_id)
    try:
        transcript = voice.transcribe(file_id)
    except ai.AIRateLimited as e:
        print(f"voice rate limited: {e}")
        if _enqueue_voice(user, chat_id, voice_msg):
            n = repo.count_pending_voices(user["id"], chat_id)
            _update_voice_status(user, chat_id, messages.TRANSCRIBE_BUSY.format(n=n))
        return
    except (ai.AIError, voice.VoiceError) as e:
        print(f"voice failed: {type(e).__name__}: {e}")
        tg.send_message(chat_id, messages.TRANSCRIBE_FAILED)
        return
    if not transcript:
        tg.send_message(chat_id, messages.TRANSCRIBE_EMPTY)
        return
    start_task_input(user, chat_id, transcript, target_date, group_id, transcript=transcript)


def handle_private_voice(chat_id, tg_user, voice_msg):
    user = _auth_user(tg_user)
    if not user:
        tg.send_message(chat_id, messages.NOT_AUTHORIZED)
        return
    _handle_voice(user, chat_id, _extract_voice(voice_msg))


def handle_group_voice(chat_id, tg_user, msg):
    if not config.is_allowed_group(chat_id):
        tg.send_message(chat_id, messages.group_not_allowed(chat_id))
        return
    if not config.is_allowed_user(tg_user["id"]):
        tg.send_message(chat_id, messages.USER_NOT_AUTHORIZED_GROUP)
        return
    voice_msg = _extract_voice(msg)
    reply_from = (voice_msg.get("reply_to_message") or {}).get("from") or {}
    if not reply_from.get("is_bot"):
        return  # only group voice that replies to the bot is handled
    user = _auth_user(tg_user)
    if not user:
        return
    group = repo.ensure_group(chat_id, (voice_msg.get("chat") or {}).get("title"))
    repo.link_membership(user["id"], group["id"])
    _handle_voice(user, chat_id, voice_msg, group_id=group["id"])


def retry_voice(user, chat_id, tg_msg=None):
    """Drain the user's voice queue oldest -> newest (cap VOICE_DRAIN_MAX)."""
    if not config.VOICE_ENABLED:
        tg.send_message(chat_id, messages.VOICE_DISABLED)
        return
    reply_voice = ((tg_msg or {}).get("reply_to_message") or {}).get("voice")

    pending = repo.list_pending_voices(user["id"], chat_id) or repo.list_pending_voices(user["id"])
    if not pending:
        if reply_voice:
            _handle_voice(user, chat_id, _extract_voice({"voice": reply_voice}))
            return
        tg.send_message(chat_id, messages.TRANSCRIBE_NONE_PENDING)
        return

    total = len(pending)
    processed = 0
    hit_limit = False
    for i, row in enumerate(pending[: config.VOICE_DRAIN_MAX], 1):
        st = repo.set_state_status(row["id"], "processing")
        if not st:
            continue
        origin_chat = row.get("chat_id") or chat_id
        try:
            transcript = voice.transcribe(st.get("file_id"))
        except ai.AIRateLimited as e:
            print(f"voice retry rate limited: {e}")
            repo.set_state_status(row["id"], "queued")
            hit_limit = True
            break
        except (ai.AIError, voice.VoiceError) as e:
            print(f"voice retry failed: {type(e).__name__}: {e}")
            repo.delete_state(row["id"])
            tg.send_message(origin_chat, messages.TRANSCRIBE_FAILED)
            continue
        repo.delete_state(row["id"])
        processed += 1
        if not transcript:
            tg.send_message(origin_chat, messages.TRANSCRIBE_EMPTY)
            continue
        start_task_input(
            user,
            origin_chat,
            transcript,
            _tomorrow(),
            _group_id_for_chat(user, origin_chat),
            transcript=transcript,
            label=messages.RECORDING_LABEL.format(i=i, n=total),
        )

    remaining = repo.count_pending_voices(user["id"])
    if remaining > 0:
        if processed == 0 and hit_limit:
            _update_voice_status(user, chat_id, messages.TRANSCRIBE_BUSY.format(n=remaining))
        else:
            _update_voice_status(user, chat_id, messages.TRANSCRIBE_PARTIAL.format(ok=processed, n=total))
    else:
        _clear_voice_status(user, delete_message=True)


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
    cb_msg = callback_query.get("message") or {}
    chat_id = (cb_msg.get("chat") or {}).get("id")
    if data == "retry:pending":
        tg.answer_callback_query(cq_id, "Retrying...")
        retry_voice(user, chat_id, None)
        return
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