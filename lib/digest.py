from datetime import date, datetime, timezone

from zoneinfo import ZoneInfo

from lib.config import GROUP_TIMEZONE, ADMIN_USER_ID
from lib.repo import (
    list_groups,
    get_group_members,
    get_primary_group_id,
    get_group,
)
from lib.repo import list_reminders, reminders_due_today, list_daily_tasks
from lib.tg import escape, split_text


def _now_local():
    return datetime.now(ZoneInfo(GROUP_TIMEZONE))


def today_local_str():
    return _now_local().date().isoformat()


def weekday_iso(d=None):
    if d is None:
        d = _now_local().date()
    # Monday=1 ... Sunday=7
    return d.isoweekday()


def iso_date_for_group_now():
    return _now_local().date()


def build_digest(group):
    tz = ZoneInfo(GROUP_TIMEZONE)
    today = _now_local().date()
    wd = today.isoweekday()

    members = get_group_members(group["id"])
    # ensure admin included even if no membership? if group known, admin should join.
    lines = []
    lines.append(f"📋 Today's reminders — {today.strftime('%a, %b %d')}")
    lines.append("")

    for u in members:
        title = u.get("display_name") or u.get("username") or f"User {u['tg_user_id']}"
        mention = f"@{u['username']}" if u.get("username") else title
        lines.append(f"👤 {mention}")
        # personal defaults
        prefs = list_reminders(user_id=u["id"])
        due = reminders_due_today(prefs, wd)
        # daily tasks today
        tasks = list_daily_tasks(user_id=u["id"], group_id=group["id"], for_date=today.isoformat())
        if not due and not tasks:
            lines.append("  • (no tasks)")
        for r in sorted(due, key=lambda x: (x.get("time_of_day") is None, x.get("time_of_day") or "")):
            t = r.get("time_of_day")
            tstr = (str(t)[:5]) if t else "anytime"
            lines.append(f"  • {escape(tstr)} {escape(r['title'])}")
        for t in tasks:
            time_str = (str(t.get("time_of_day"))[:5]) if t.get("time_of_day") else "anytime"
            mark = " ✔" if t.get("done") else ""
            lines.append(f"  • {escape(time_str)} {escape(t['title'])}{mark}")
        lines.append("")

    # shared
    shared = list_reminders(shared=True, group_id=group["id"])
    shared_due = reminders_due_today(shared, wd)
    if shared_due:
        lines.append("🤝 Shared")
        for r in sorted(shared_due, key=lambda x: (x.get("time_of_day") is None, x.get("time_of_day") or "")):
            t = r.get("time_of_day")
            tstr = (str(t)[:5]) if t else "anytime"
            lines.append(f"  • {escape(tstr)} {escape(r['title'])}")
        lines.append("")

    lines.append("Send tomorrow's tasks tonight via DM to the bot.")
    return "\n".join(lines)


def render_digests_all():
    out = []
    for g in list_groups(active_only=True):
        out.append((g, build_digest(g)))
    return out
