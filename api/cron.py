import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, HTTPException

from lib import config, tg, digest, repo
from lib.digest import iso_date_for_group_now

app = FastAPI()

CRON_PATH = "/api/cron"


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
    # Vercel cron user-agent fallback for personal deployments
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
                tg.send_message(g["tg_group_id"], chunk)
            repo.set_setting(key, today_local)
            sent += 1
        except Exception as e:
            errors.append(f"{g.get('title')}: {repr(e)}")
    return {"ok": True, "today_local": today_local, "sent": sent, "skipped": skipped, "errors": errors}


@app.get("/api/health")
async def health():
    return {"ok": True}