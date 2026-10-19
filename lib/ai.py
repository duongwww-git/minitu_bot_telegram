"""Google Gemini client (v2 AI).

Slot A: text -> tasks (structured JSON) via Gemini Flash.
Slot B: voice -> text via Gemini Transcribe.

Uses the REST API over httpx so no extra dependency is required. All failures
raise AIError (or AIRateLimited for HTTP 429) so callers can fall back to the
v1 rule parser or queue the request for retry.
"""

import base64
import json
import re
from datetime import date, datetime

import httpx

from lib import config

_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_TIMEOUT_SECONDS = 30


class AIError(Exception):
    pass


class AIRateLimited(AIError):
    pass


_TASK_SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "time": {"type": "string"},
                    "date": {"type": "string"},
                    "priority": {"type": "integer"},
                    "notes": {"type": "string"},
                },
                "required": ["title"],
            },
        }
    },
    "required": ["tasks"],
}

_PARSE_PROMPT = (
    "You convert a short note into a list of tasks.\n"
    "Return JSON with a 'tasks' array. Each task has:\n"
    "- title (string, required, short and actionable)\n"
    "- time (\"HH:MM\" 24-hour, or null when no time is stated)\n"
    "- date (\"YYYY-MM-DD\", or null when no date is stated or implied)\n"
    "- priority (1-3 integer, 1 = normal; optional)\n"
    "- notes (optional short string)\n"
    "\n"
    "Today is {today} ({weekday}); the timezone is {tz}.\n"
    "\n"
    "Date rules:\n"
    "- Resolve relative wording against today: today/tonight (\"hôm nay\"), tomorrow "
    "(\"ngày mai\", \"mai\"), the day after tomorrow (\"ngày mốt\", \"mốt\"), "
    "weekday names (\"thứ 2\"..\"chủ nhật\", \"Monday\"..\"Sunday\") meaning the next "
    "occurrence with today counting when it matches, weekend (\"cuối tuần\", \"weekend\") "
    "meaning the coming Saturday, and \"tuần sau\"/\"next week\" meaning the same weekday "
    "next week.\n"
    "- Numeric dates are day/month: \"20/10\" is 20 October and \"10/5\" is 10 May. "
    "English month names (\"Oct 20\", \"20 October\") and ISO dates also apply.\n"
    "- Never invent a date the note does not state or clearly imply; use null instead.\n"
    "- If the named date has already passed, return it as written so the app can flag it; "
    "do not roll it forward and do not silently drop it.\n"
    "\n"
    "Rules: never invent tasks the note does not contain; return an empty array when there "
    "are no tasks; never guess a time that is not stated.\n"
    "Note: {text}"
)

_TRANSCRIBE_PROMPT = (
    "Transcribe this audio message. Return only the transcript text, with no "
    "commentary, labels, or quotes. Keep the original language."
)


def enabled():
    return bool(config.GEMINI_API_KEY)


def _generate(model, parts, response_schema=None, temperature=0.2, timeout=_TIMEOUT_SECONDS):
    if not config.GEMINI_API_KEY:
        raise AIError("GEMINI_API_KEY not configured")
    generation_config = {"temperature": temperature}
    if response_schema is not None:
        generation_config["responseMimeType"] = "application/json"
        generation_config["responseSchema"] = response_schema
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": generation_config,
    }
    try:
        r = httpx.post(
            f"{_API_BASE}/models/{model}:generateContent",
            params={"key": config.GEMINI_API_KEY},
            json=payload,
            timeout=timeout,
        )
    except httpx.HTTPError as e:
        raise AIError(f"{model} request failed: {e}") from e
    if r.status_code == 429:
        raise AIRateLimited(f"{model}: {r.text[:200]}")
    if r.status_code >= 400:
        raise AIError(f"{model} HTTP {r.status_code}: {r.text[:200]}")
    return _extract_text(r.json())


def _extract_text(data):
    try:
        candidates = data.get("candidates") or []
        parts = candidates[0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError, TypeError) as e:
        raise AIError(f"unexpected response: {str(data)[:200]}") from e


_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATE_WINDOW_DAYS = 365
_DATE_EMPTY = ("", "null", "none", "n/a")


def _resolve_today(today_iso=None):
    if today_iso:
        try:
            return date.fromisoformat(str(today_iso)[:10])
        except ValueError:
            pass
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo(config.GROUP_TIMEZONE)).date()


def _clean_date(value, today):
    """Accept only an ISO date inside [today, today + 365]. Past/invalid -> None."""
    text = str(value or "").strip()
    if text.lower() in _DATE_EMPTY or not _DATE_RE.match(text):
        return None
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return None
    if parsed < today or (parsed - today).days > _DATE_WINDOW_DAYS:
        return None
    return parsed.isoformat()


def _clean_time(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in ("null", "none", "n/a"):
        return None
    m = _TIME_RE.match(text)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def parse_tasks_ai(text, today_iso=None, tz_name=None):
    """Slot A: parse free text into tasks. Returns a list, or None on failure.

    ``today_iso`` must be the *local* date (Vercel runs in UTC), otherwise the
    model resolves "today" one day early between 00:00 and 07:00 GMT+7.
    """
    if not config.AI_ENABLED or not (text or "").strip():
        return None
    today = _resolve_today(today_iso)
    prompt = _PARSE_PROMPT.format(
        today=today.isoformat(),
        weekday=today.strftime("%A"),
        tz=tz_name or config.GROUP_TIMEZONE,
        text=text.strip(),
    )
    try:
        raw = _generate(
            config.AI_MODEL_TEXT, [{"text": prompt}], response_schema=_TASK_SCHEMA, temperature=0
        )
        data = json.loads(raw)
    except (AIError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    tasks = []
    for item in data.get("tasks") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        task = {"title": title, "time": _clean_time(item.get("time"))}
        raw_date = item.get("date")
        clean_date = _clean_date(raw_date, today)
        if clean_date:
            task["date"] = clean_date
        elif str(raw_date or "").strip().lower() not in _DATE_EMPTY:
            # the model named a date we cannot use (past or malformed)
            task["date_rejected"] = True
        try:
            priority = int(item.get("priority") or 0)
            if 1 <= priority <= 3:
                task["priority"] = priority
        except (TypeError, ValueError):
            pass
        if item.get("notes"):
            task["notes"] = str(item["notes"]).strip()
        tasks.append(task)
    return tasks or None


def transcribe(audio_bytes, mime_type="audio/ogg"):
    """Slot B: voice bytes -> text. Raises AIRateLimited on HTTP 429."""
    if not config.GEMINI_API_KEY:
        raise AIError("GEMINI_API_KEY not configured")
    encoded = base64.b64encode(audio_bytes).decode("ascii")
    parts = [
        {"text": _TRANSCRIBE_PROMPT},
        {"inline_data": {"mime_type": mime_type, "data": encoded}},
    ]
    models = [config.AI_MODEL_TRANSCRIBE]
    if config.AI_MODEL_TEXT and config.AI_MODEL_TEXT != config.AI_MODEL_TRANSCRIBE:
        # Fall back to the text model (also multimodal) if the dedicated
        # transcription model is unavailable on this API version.
        models.append(config.AI_MODEL_TEXT)
    last_error = None
    for model in models:
        try:
            text = _generate(model, parts)
        except AIRateLimited:
            raise
        except AIError as e:
            print(f"transcribe model {model} failed: {e}")
            last_error = e
            continue
        if text:
            return text
    raise last_error or AIError("transcription failed")
