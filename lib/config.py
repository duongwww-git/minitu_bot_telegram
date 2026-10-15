import os


def env(name, default=None, required=False):
    val = os.environ.get(name, default)
    if required and not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val


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
DIGEST_HOUR_LOCAL = int(env("DIGEST_HOUR_LOCAL", "6"))


def is_allowed_user(tg_user_id):
    return tg_user_id in ALLOWED_USER_IDS if ALLOWED_USER_IDS else True


def is_allowed_group(tg_group_id):
    return tg_group_id in ALLOWED_GROUP_IDS if ALLOWED_GROUP_IDS else True


def is_admin(tg_user_id):
    return ADMIN_USER_ID is not None and tg_user_id == ADMIN_USER_ID
