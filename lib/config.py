import os


def env(name, default=None, required=False):
    val = os.environ.get(name, default)
    if required and not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val


def env_bool(name, default=False):
    val = os.environ.get(name)
    if val is None or str(val).strip() == "":
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def env_int(name, default):
    try:
        return int(str(os.environ.get(name, default)).strip())
    except (TypeError, ValueError):
        return default


def parse_ids(raw):
    if not raw:
        return []
    out = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out


BOT_TOKEN = env("BOT_TOKEN", "")
WEBHOOK_SECRET = env("WEBHOOK_SECRET", "")
CRON_SECRET = env("CRON_SECRET", "")
SUPABASE_URL = env("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = env("SUPABASE_SERVICE_ROLE_KEY", "")
ALLOWED_USER_IDS = parse_ids(env("ALLOWED_USER_IDS", ""))
ALLOWED_GROUP_IDS = parse_ids(env("ALLOWED_GROUP_IDS", ""))
ADMIN_USER_ID_RAW = env("ADMIN_USER_ID", "")
ADMIN_USER_ID = int(ADMIN_USER_ID_RAW) if str(ADMIN_USER_ID_RAW).strip().isdigit() else None
BOT_USERNAME = env("BOT_USERNAME", "")
GROUP_TIMEZONE = env("GROUP_TIMEZONE", "Asia/Bangkok")
DIGEST_HOUR_LOCAL = env_int("DIGEST_HOUR_LOCAL", 6)

# ---- v2: Google Gemini AI ----
# Slot A = Gemini Flash (text -> tasks), Slot B = Gemini Transcribe (voice -> text).
GEMINI_API_KEY = env("GEMINI_API_KEY", "")
AI_MODEL_TEXT = env("AI_MODEL_TEXT", "gemini-3.8-flash")
AI_MODEL_TRANSCRIBE = env("AI_MODEL_TRANSCRIBE", "gemini-3.5-transcribe")
USE_AI = env_bool("USE_AI", False)
VOICE_QUEUE_MAX = env_int("VOICE_QUEUE_MAX", 5)
VOICE_DRAIN_MAX = env_int("VOICE_DRAIN_MAX", 3)
VOICE_RETRY_TTL_HOURS = env_int("VOICE_RETRY_TTL_HOURS", 48)

# AI text parsing is opt-in (USE_AI flag). Voice transcription needs a Gemini key.
AI_ENABLED = USE_AI and bool(GEMINI_API_KEY)
VOICE_ENABLED = bool(GEMINI_API_KEY)


def is_allowed_user(tg_user_id):
    return tg_user_id in ALLOWED_USER_IDS if ALLOWED_USER_IDS else True


def is_allowed_group(tg_group_id):
    return tg_group_id in ALLOWED_GROUP_IDS if ALLOWED_GROUP_IDS else True


def is_admin(tg_user_id):
    return ADMIN_USER_ID is not None and tg_user_id == ADMIN_USER_ID
