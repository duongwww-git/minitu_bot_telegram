import json
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_FILE = os.path.join(_ROOT, "config.defaults.json")

try:
    with open(_CONFIG_FILE) as f:
        _FILE_CONFIG = json.load(f)
except Exception:
    _FILE_CONFIG = {}


def env(name, default=None, required=False):
    """Read a secret from the environment only (never from config.defaults.json)."""
    val = os.environ.get(name, default)
    if required and not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val


def _config_value(name, default):
    """Precedence: environment variable > config.defaults.json > built-in default."""
    env_val = os.environ.get(name)
    if env_val is not None and str(env_val).strip() != "":
        return env_val
    if name in _FILE_CONFIG:
        return _FILE_CONFIG[name]
    return default


def cfg_str(name, default=None):
    val = _config_value(name, default)
    return None if val is None else str(val)


def cfg_bool(name, default=False):
    val = _config_value(name, default)
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def cfg_int(name, default):
    try:
        return int(str(_config_value(name, default)).strip())
    except (TypeError, ValueError):
        return default


def config_file_loaded():
    """True when config.defaults.json was found and parsed at startup."""
    return bool(_FILE_CONFIG)


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


# ---- secrets (set in Vercel env vars; never commit these) ----
BOT_TOKEN = env("BOT_TOKEN", "")
WEBHOOK_SECRET = env("WEBHOOK_SECRET", "")
CRON_SECRET = env("CRON_SECRET", "")
SUPABASE_URL = env("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = env("SUPABASE_SERVICE_ROLE_KEY", "")
GEMINI_API_KEY = env("GEMINI_API_KEY", "")

# ---- non-secret, deployment-specific (env vars, or leave blank and set via /join) ----
ALLOWED_USER_IDS = parse_ids(env("ALLOWED_USER_IDS", ""))
ALLOWED_GROUP_IDS = parse_ids(env("ALLOWED_GROUP_IDS", ""))
ADMIN_USER_ID_RAW = env("ADMIN_USER_ID", "")
ADMIN_USER_ID = int(ADMIN_USER_ID_RAW) if str(ADMIN_USER_ID_RAW).strip().isdigit() else None
BOT_USERNAME = env("BOT_USERNAME", "")

# ---- non-secret tunables (defaults live in config.defaults.json) ----
# Slot A = Gemini Flash (text -> tasks), Slot B = Gemini Transcribe (voice -> text).
GROUP_TIMEZONE = cfg_str("GROUP_TIMEZONE", "Asia/Bangkok")
DIGEST_HOUR_LOCAL = cfg_int("DIGEST_HOUR_LOCAL", 6)
AI_MODEL_TEXT = cfg_str("AI_MODEL_TEXT", "gemini-3.8-flash")
AI_MODEL_TRANSCRIBE = cfg_str("AI_MODEL_TRANSCRIBE", "gemini-3.5-transcribe")
USE_AI = cfg_bool("USE_AI", False)
VOICE_QUEUE_MAX = cfg_int("VOICE_QUEUE_MAX", 5)
VOICE_DRAIN_MAX = cfg_int("VOICE_DRAIN_MAX", 3)
VOICE_RETRY_TTL_HOURS = cfg_int("VOICE_RETRY_TTL_HOURS", 48)

# AI text parsing is opt-in (USE_AI flag). Voice transcription needs a Gemini key.
AI_ENABLED = USE_AI and bool(GEMINI_API_KEY)
VOICE_ENABLED = bool(GEMINI_API_KEY)


def is_allowed_user(tg_user_id):
    return tg_user_id in ALLOWED_USER_IDS if ALLOWED_USER_IDS else True


def is_allowed_group(tg_group_id):
    return tg_group_id in ALLOWED_GROUP_IDS if ALLOWED_GROUP_IDS else True


def is_admin(tg_user_id):
    return ADMIN_USER_ID is not None and tg_user_id == ADMIN_USER_ID
