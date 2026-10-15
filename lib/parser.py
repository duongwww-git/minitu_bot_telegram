import re


_TIME_PATTERNS = [
    re.compile(r"(\d{1,2}):(\d{2})\s*(am|pm)?", re.I),
    re.compile(r"(\d{1,2})\s*(am|pm)", re.I),
]


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


def _extract_time(seg):
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


def parse_tasks(text):
    if not text:
        return []
    tasks = []
    for seg in re.split(r"[;\n,]+", text):
        seg = seg.strip()
        if not seg:
            continue
        title, time_str, _ = _extract_time(seg)
        title = title.strip()
        if not title:
            continue
        tasks.append({"title": title, "time": time_str})
    # de-dup exact
    seen = set()
    out = []
    for t in tasks:
        key = (t["title"].lower(), t["time"])
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def format_tasks(tasks):
    lines = []
    for i, t in enumerate(tasks, 1):
        time_part = f" — {t['time']}" if t.get("time") else " — (no time)"
        lines.append(f"{i}. {t['title']}{time_part}")
    return "\n".join(lines)
