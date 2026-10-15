import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request, HTTPException

from lib import config, tg, handlers

app = FastAPI()


def _verify_webhook(request: Request):
    if config.WEBHOOK_SECRET:
        token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if token != config.WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="invalid webhook secret")


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
            text = (msg.get("text") or "").strip()
            if chat_type == "private":
                handlers.handle_private_message(chat_id, tg_user, text)
            else:
                handlers.handle_group_message(chat_id, tg_user, text, msg)
        # other update types ignored in v1
    except Exception as e:
        # Acknowledge to Telegram to avoid retries storm; log
        print(f"webhook error: {repr(e)}")
    return {"ok": True}


@app.get("/api/webhook")
async def webhook_health():
    return {"ok": True, "service": "ai-agent-reminder v1"}
