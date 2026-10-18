import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Request, HTTPException

from lib import config, tg, handlers, digest, repo

APP_VERSION = "0.2.0"

app = FastAPI()


def _verify_webhook(request: Request):
    if config.WEBHOOK_SECRET:
        token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if token != config.WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="invalid webhook secret")


@app.get("/api/webhook")
async def webhook_health():
    return {"ok": True, "service": "ai-agent-reminder v2"}


@app.post("/api/webhook")
async def webhook(request: Request):
    _verify_webhook(request)
    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    try:
        if "callback_query" in update:
            handlers.handle_callback(update["callback_query"])
        elif "message" in update:
            msg = update["message"]
            chat = msg.get("chat", {})
            chat_id = chat.get("id")
            chat_type = chat.get("type", "private")
            tg_user = msg.get("from", {})
            if msg.get("voice"):
                if chat_type == "private":
                    handlers.handle_private_voice(chat_id, tg_user, msg)
                else:
                    handlers.handle_group_voice(chat_id, tg_user, msg)
            else:
                text = (msg.get("text") or "").strip()
                if chat_type == "private":
                    handlers.handle_private_message(chat_id, tg_user, text, msg)
                else:
                    handlers.handle_group_message(chat_id, tg_user, text, msg)
    except Exception as e:
        print(f"webhook error: {repr(e)}")
    return {"ok": True}


def _authorized(request: Request):
    secret = config.CRON_SECRET
    if not secret:
        return True
    auth = request.headers.get("Authorization", "")
    if auth == f"Bearer {secret}":
        return True
    q = request.query_params.get("secret")
    if q and q == secret:
        return True
    if request.headers.get("User-Agent", "").startswith("vercel-cron"):
        return True
    return False


@app.get("/api/cron")
async def cron(request: Request):
    if not _authorized(request):
        raise HTTPException(status_code=401, detail="unauthorized")
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(config.GROUP_TIMEZONE)
    today_local = datetime.now(tz).date().isoformat()

    sent = 0
    skipped = 0
    errors = []
    groups = repo.list_groups(active_only=True)
    for g in groups:
        key = f"digest_sent:{g['id']}"
        last = repo.get_setting(key)
        if last == today_local:
            skipped += 1
            continue
        try:
            text = digest.build_digest(g)
            for chunk in tg.split_text(text):
                tg.send_message(g["tg_group_id"], chunk, parse_mode="HTML")
            repo.set_setting(key, today_local)
            sent += 1
        except Exception as e:
            resp_text = getattr(getattr(e, 'response', None), 'text', None)
            errors.append(f"group_id={g.get('tg_group_id')}: {repr(e)} | body={resp_text}")

    cleaned = 0
    try:
        cleaned = repo.cleanup_expired_states()
    except Exception as e:
        errors.append(f"cleanup: {repr(e)}")

    return {
        "ok": True,
        "today_local": today_local,
        "sent": sent,
        "skipped": skipped,
        "cleaned_states": cleaned,
        "errors": errors,
    }


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/debug")
async def debug():
    from lib import config as cfg

    return {
        "app_version": APP_VERSION,
        "git_commit": (os.environ.get("VERCEL_GIT_COMMIT_SHA") or "")[:8],
        "vercel_env": os.environ.get("VERCEL_ENV", ""),
        "webhook_secret_set": bool(cfg.WEBHOOK_SECRET),
        "webhook_secret_length": len(cfg.WEBHOOK_SECRET or ""),
        "bot_token_set": bool(cfg.BOT_TOKEN),
        "db_url_set": bool(cfg.SUPABASE_URL),
        "db_key_set": bool(cfg.SUPABASE_SERVICE_ROLE_KEY),
        "allowed_users": cfg.ALLOWED_USER_IDS,
        "allowed_groups": cfg.ALLOWED_GROUP_IDS,
        "admin": cfg.ADMIN_USER_ID,
        "use_ai": cfg.USE_AI,
        "ai_enabled": cfg.AI_ENABLED,
        "voice_enabled": cfg.VOICE_ENABLED,
        "gemini_key_set": bool(cfg.GEMINI_API_KEY),
        "ai_model_text": cfg.AI_MODEL_TEXT,
        "ai_model_transcribe": cfg.AI_MODEL_TRANSCRIBE,
        "voice_queue_max": cfg.VOICE_QUEUE_MAX,
        "config_file_loaded": cfg.config_file_loaded(),
    }
