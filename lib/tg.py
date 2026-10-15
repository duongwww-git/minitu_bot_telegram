import html as _html

import httpx

from lib.config import BOT_TOKEN, WEBHOOK_SECRET


TG_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"


def _post(method, payload):
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not configured")
    r = httpx.post(f"{TG_BASE}/{method}", json=payload, timeout=20)
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        print(f"Telegram {method} failed body={r.text!r}")
        raise
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {data}")
    return data.get("result")


def send_message(chat_id, text, reply_markup=None, parse_mode=None):
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return _post("sendMessage", payload)


def answer_callback_query(callback_query_id, text=None, show_alert=False):
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    payload["show_alert"] = show_alert
    return _post("answerCallbackQuery", payload)


def delete_message(chat_id, message_id):
    try:
        _post("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
    except Exception:
        pass


def get_me():
    return _post("getMe", {})


_BOT_USERNAME_CACHE = None


def get_bot_username():
    global _BOT_USERNAME_CACHE
    if _BOT_USERNAME_CACHE:
        return _BOT_USERNAME_CACHE
    from lib.config import BOT_USERNAME

    if BOT_USERNAME:
        _BOT_USERNAME_CACHE = BOT_USERNAME.lstrip("@")
        return _BOT_USERNAME_CACHE
    try:
        me = get_me()
        if me and me.get("username"):
            _BOT_USERNAME_CACHE = me["username"]
            return _BOT_USERNAME_CACHE
    except Exception:
        pass
    return ""


def escape(s):
    return _html.escape(str(s), quote=False)


def split_text(text, max_len=4000):
    if len(text) <= max_len:
        return [text]
    chunks = []
    cur = ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > max_len:
            if cur:
                chunks.append(cur)
            cur = line
        else:
            cur = (cur + "\n" + line) if cur else line
    if cur:
        chunks.append(cur)
    return chunks
