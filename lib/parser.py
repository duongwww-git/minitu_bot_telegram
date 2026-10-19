import re
from datetime import date, timedelta


_TIME_PATTERNS = [
    re.compile(r"(\d{1,2}):(\d{2})\s*(am|pm)?", re.I),
    re.compile(r"(\d{1,2})\s*(am|pm)", re.I),
]

# v2.1: the rule parser intentionally understands only these day expressions.
# Explicit dates, weekdays and "tuần sau" are handled by Slot A (Gemini) only,
# so the fallback stays predictable when AI is unavailable.
_RELATIVE_DAYS = [
    (re.compile(r"\b(day after tomorrow)\b", re.I), 2),
    (re.compile(r"\b(ngày kia|ngay kia)\b", re.I), 2),
    (re.compile(r"\b(ngày mốt|ngay mot)\b", re.I), 2),
    (re.compile(r"\b(ngày mai|ngay mai)\b", re.I), 1),
    (re.compile(r"\b(tomorrow)\b", re.I), 1),
    (re.compile(r"\b(ngày hôm nay|ngay hom nay|hôm nay|hom nay|today|tonight)\b", re.I), 0),
    (re.compile(r"\bmốt\b", re.I), 2),
    (re.compile(r"\bmai\b", re.I), 1),
]
_WEEKEND_RE = re.compile(r"\b(cuối tuần này|cuối tuần|cuoi tuan|this weekend|weekend)\b", re.I)

# A segment that looks like a date must not have its trailing number read as a time
# ("họp ngày 20 tháng 10" must not become 10:00).
_DATEISH_RE = re.compile(r"\d{1,2}\s*[/-]\s*\d{1,2}|\b(ngày|ngay|tháng|thang)\b", re.I)


def _clean_title(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"^(on|at|for|from|vào|vao|ngày|ngay|hẹn|hen)\s+", "", text, flags=re.I)
    return text.strip(" ,.-")


def _upcoming_saturday(today):
    """The coming Saturday; today itself counts when today is Saturday."""
    wd = today.isoweekday()  # Mon=1 ... Sun=7
    if wd == 6:
        return today
    if wd == 7:
        return today + timedelta(days=6)
    return today + timedelta(days=6 - wd)


def _extract_date(seg, today):
    """Return (iso_date_or_None, segment_without_the_date_phrase)."""
    for pattern, offset in _RELATIVE_DAYS:
        m = pattern.search(seg)
        if m:
            return (today + timedelta(days=offset)).isoformat(), _clean_title(
                seg[: m.start()] + " " + seg[m.end():]
            )
    m = _WEEKEND_RE.search(seg)
    if m:
        return _upcoming_saturday(today).isoformat(), _clean_title(
            seg[: m.start()] + " " + seg[m.end():]
        )
    return None, seg


def _normalize_time(hour, minute, ampm):
    hour = int(hour)
    minute = int(minute) if minute is not None else 0
    ampm = (ampm or "").lower()
    if ampm == "am":
        if hour == 12:
            hour = 0
    elif ampm == "pm":
        if hour != 12:
            hour += 12
    elif ampm == "":
        # bare hour/HH:MM treated as 24-hour when hour <= 23
        pass
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def _extract_time(seg, allow_bare_hour=True):
    # Try HH:MM (am/pm optional)
    m = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)?", seg, re.I)
    if m:
        time_str = _normalize_time(m.group(1), m.group(2), m.group(3))
        title = (seg[: m.start()] + " " + seg[m.end() :]).strip()
        title = re.sub(r"\s+", " ", title).strip(" ,.-")
        title = re.sub(r"^(at|on|to)\s+", "", title, flags=re.I)
        return title, time_str, m.group(0)
    m = re.search(r"(\d{1,2})\s*(am|pm)", seg, re.I)
    if m:
        time_str = _normalize_time(m.group(1), 0, m.group(2))
        title = (seg[: m.start()] + " " + seg[m.end() :]).strip()
        title = re.sub(r"\s+", " ", title).strip(" ,.-")
        title = re.sub(r"^(at|on|to)\s+", "", title, flags=re.I)
        return title, time_str, m.group(0)
    if not allow_bare_hour:
        return seg.strip(), None, None
    # bare hour like "gym 18"
    m = re.search(r"\b(\d{1,2})\b(?!:)", seg)
    # only treat as time if segment has a trailing/leading number and a word
    m2 = re.search(r"^(.*?)(?:\s+(\d{1,2}))\s*$", seg.strip())
    if m2 and m2.group(1).strip():
        h = int(m2.group(2))
        if 0 <= h <= 23:
            title = m2.group(1).strip()
            title = re.sub(r"^(at|on|to)\s+", "", title, flags=re.I)
            return title, f"{h:02d}:00", m2.group(2)
    return seg.strip(), None, None


def parse_tasks(text, today=None):
    if not text:
        return []
    today = today or date.today()
    tasks = []
    for seg in re.split(r"[;\n,]+", text):
        seg = seg.strip()
        if not seg:
            continue
        date_str, seg = _extract_date(seg, today)
        allow_bare_hour = not _DATEISH_RE.search(seg)
        title, time_str, _ = _extract_time(seg, allow_bare_hour=allow_bare_hour)
        title = title.strip()
        if not title:
            continue
        task = {"title": title, "time": time_str}
        if date_str:
            task["date"] = date_str
        tasks.append(task)
    # de-dup exact
    seen = set()
    out = []
    for t in tasks:
        key = (t["title"].lower(), t["time"], t.get("date"))
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def format_tasks(tasks, today=None):
    from lib import messages

    return messages.render_tasks(tasks, today=today, numbered=True)
