import os
from datetime import datetime, timezone, timedelta
from lib.config import ADMIN_USER_ID, GROUP_TIMEZONE
from lib.db import get_db


def _db():
    return get_db()


def upsert_user(tg_user_id, username=None, display_name=None):
    db = _db()
    existing = db.table("users").select("*").eq("tg_user_id", tg_user_id).execute()
    is_admin = (ADMIN_USER_ID is not None and tg_user_id == ADMIN_USER_ID)
    payload = {
        "tg_user_id": tg_user_id,
        "username": username,
        "display_name": display_name or username,
        "is_admin": is_admin,
    }
    if existing.data:
        row = existing.data[0]
        db.table("users").update(
            {"username": username, "display_name": display_name or row.get("display_name"), "is_admin": is_admin}
        ).eq("id", row["id"]).execute()
        row["is_admin"] = is_admin
        if username is not None:
            row["username"] = username
        if display_name is not None:
            row["display_name"] = display_name
        return row
    res = db.table("users").insert(payload).execute()
    return res.data[0]


def get_user(tg_user_id):
    db = _db()
    res = db.table("users").select("*").eq("tg_user_id", tg_user_id).execute()
    return res.data[0] if res.data else None


def get_user_by_id(user_id):
    db = _db()
    res = db.table("users").select("*").eq("id", user_id).execute()
    return res.data[0] if res.data else None


def ensure_group(tg_group_id, title=None):
    db = _db()
    existing = db.table("groups").select("*").eq("tg_group_id", tg_group_id).execute()
    if existing.data:
        row = existing.data[0]
        if title and title != row.get("title"):
            db.table("groups").update({"title": title}).eq("id", row["id"]).execute()
            row["title"] = title
        return row
    payload = {"tg_group_id": tg_group_id, "title": title, "active": True}
    res = db.table("groups").insert(payload).execute()
    return res.data[0]


def link_membership(user_id, group_id):
    db = _db()
    try:
        db.table("memberships").insert({"user_id": user_id, "group_id": group_id}).execute()
    except Exception:
        pass  # already linked


def get_group_by_tg(tg_group_id):
    db = _db()
    res = db.table("groups").select("*").eq("tg_group_id", tg_group_id).execute()
    return res.data[0] if res.data else None


def get_group(group_id):
    db = _db()
    res = db.table("groups").select("*").eq("id", group_id).execute()
    return res.data[0] if res.data else None


def list_groups(active_only=True):
    db = _db()
    q = db.table("groups").select("*")
    if active_only:
        q = q.eq("active", True)
    return q.execute().data or []


def get_primary_group_id(user_id):
    db = _db()
    res = db.table("memberships").select("group_id").eq("user_id", user_id).limit(1).execute()
    if res.data:
        return res.data[0]["group_id"]
    return None


def get_group_members(group_id):
    db = _db()
    ms = db.table("memberships").select("user_id").eq("group_id", group_id).execute().data or []
    users = []
    for m in ms:
        u = get_user_by_id(m["user_id"])
        if u:
            users.append(u)
    return users


# -------- settings --------

def get_setting(key):
    db = _db()
    res = db.table("settings").select("value").eq("key", key).execute()
    return res.data[0]["value"] if res.data else None


def set_setting(key, value):
    db = _db()
    db.table("settings").upsert({"key": key, "value": str(value)}).execute()


# -------- reminders (defaults) --------

WEEKDAYS_ALL = [1, 2, 3, 4, 5, 6, 7]


def add_reminder(user_id=None, group_id=None, title="", time_of_day=None, weekdays=None, active=True):
    db = _db()
    payload = {
        "user_id": user_id,
        "group_id": group_id,
        "title": title,
        "time_of_day": time_of_day,
        "weekdays": weekdays or WEEKDAYS_ALL,
        "active": active,
    }
    res = db.table("reminders").insert(payload).execute()
    return res.data[0] if res.data else None


def list_reminders(user_id=None, group_id=None, shared=False):
    db = _db()
    q = db.table("reminders").select("*").eq("active", True)
    if shared:
        q = q.is_("user_id", "null")
        if group_id:
            q = q.eq("group_id", group_id)
    elif user_id is not None:
        q = q.eq("user_id", user_id)
    res = q.execute()
    return res.data or []


def get_reminder(reminder_id):
    db = _db()
    res = db.table("reminders").select("*").eq("id", reminder_id).execute()
    return res.data[0] if res.data else None


def remove_reminder(reminder_id):
    db = _db()
    db.table("reminders").delete().eq("id", reminder_id).execute()


def reminders_due_today(reminders, today_weekday_iso):
    # today_weekday_iso: 1..7 (Mon=1)
    out = []
    for r in reminders:
        wds = r.get("weekdays") or WEEKDAYS_ALL
        if today_weekday_iso in wds:
            out.append(r)
    return out


# -------- daily tasks --------

def add_daily_task(user_id, group_id, for_date, title, time_of_day=None):
    db = _db()
    payload = {
        "user_id": user_id,
        "group_id": group_id,
        "for_date": for_date,
        "title": title,
        "time_of_day": time_of_day,
        "done": False,
    }
    res = db.table("daily_tasks").insert(payload).execute()
    return res.data[0] if res.data else None


def list_daily_tasks(user_id=None, group_id=None, for_date=None):
    db = _db()
    q = db.table("daily_tasks").select("*")
    if user_id is not None:
        q = q.eq("user_id", user_id)
    if group_id is not None:
        q = q.eq("group_id", group_id)
    if for_date is not None:
        q = q.eq("for_date", for_date)
    res = q.execute()
    return res.data or []


def remove_daily_task(task_id):
    db = _db()
    db.table("daily_tasks").delete().eq("id", task_id).execute()


# -------- conversation state --------

def create_state(user_id, chat_id, state, expires_minutes=15):
    db = _db()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    res = db.table("conversation_state").insert(
        {"user_id": user_id, "chat_id": chat_id, "state": state, "expires_at": expires_at.isoformat()}
    ).execute()
    return res.data[0] if res.data else None


def get_state(state_id):
    db = _db()
    from datetime import datetime, timezone

    res = db.table("conversation_state").select("*").eq("id", state_id).execute()
    if not res.data:
        return None
    row = res.data[0]
    # expiry check
    try:
        exp = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
        if exp < datetime.now(timezone.utc):
            delete_state(state_id)
            return None
    except Exception:
        pass
    return row


def delete_state(state_id):
    db = _db()
    db.table("conversation_state").delete().eq("id", state_id).execute()


def update_state_json(state_id, state):
    db = _db()
    db.table("conversation_state").update({"state": state}).eq("id", state_id).execute()


def set_state_status(state_id, status):
    row = get_state(state_id)
    if not row:
        return None
    st = dict(row.get("state") or {})
    st["status"] = status
    update_state_json(state_id, st)
    return st


def cleanup_expired_states():
    db = _db()
    now_iso = datetime.now(timezone.utc).isoformat()
    res = db.table("conversation_state").delete().lt("expires_at", now_iso).execute()
    return len(res.data or [])


def delete_setting(key):
    db = _db()
    db.table("settings").delete().eq("key", key).execute()


# -------- voice retry queue (reuses conversation_state) --------

PENDING_VOICE_KIND = "pending_voice"


def _state_expired(row):
    try:
        exp = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
        return exp < datetime.now(timezone.utc)
    except Exception:
        return False


def enqueue_pending_voice(user_id, chat_id, file_id, message_id=None, duration=None, ttl_hours=None):
    from lib.config import VOICE_RETRY_TTL_HOURS

    ttl = ttl_hours or VOICE_RETRY_TTL_HOURS
    state = {
        "kind": PENDING_VOICE_KIND,
        "file_id": file_id,
        "message_id": message_id,
        "duration": duration,
        "status": "queued",
    }
    return create_state(user_id, chat_id, state, expires_minutes=int(ttl) * 60)


def list_pending_voices(user_id, chat_id=None, include_processing=False):
    """Pending voice rows for a user, oldest first."""
    db = _db()
    res = (
        db.table("conversation_state")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at")
        .execute()
    )
    out = []
    for row in res.data or []:
        st = row.get("state") or {}
        if st.get("kind") != PENDING_VOICE_KIND:
            continue
        if chat_id is not None and row.get("chat_id") != chat_id:
            continue
        if not include_processing and st.get("status") == "processing":
            continue
        if _state_expired(row):
            delete_state(row["id"])
            continue
        out.append(row)
    return out


def count_pending_voices(user_id, chat_id=None):
    return len(list_pending_voices(user_id, chat_id))
