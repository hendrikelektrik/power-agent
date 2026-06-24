import logging
import threading
import time
import requests
from power_agent.config import CONFIG
from power_agent.storage import get_setting
from power_agent.ai import ask as ai_ask

logger = logging.getLogger(__name__)

_last_update_id = 0


def _send_typing(chat_id: int):
    token = CONFIG.telegram_bot_token
    if not token:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendChatAction"
        requests.post(url, json={"chat_id": chat_id, "action": "typing"}, timeout=5)
    except Exception:
        pass


def _send_reply(chat_id: int, text: str):
    token = CONFIG.telegram_bot_token
    if not token:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        logger.error("Failed to send bot reply: %s", e)


def poll_once():
    global _last_update_id
    token = CONFIG.telegram_bot_token
    if not token:
        return
    if get_setting("bot_enabled", "1") != "1":
        return
    try:
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        params = {"timeout": 30, "offset": _last_update_id + 1}
        resp = requests.get(url, params=params, timeout=35)
        if not resp.ok:
            return
        data = resp.json()
        for update in data.get("result", []):
            _last_update_id = update["update_id"]
            msg = update.get("message")
            if not msg:
                continue
            chat_id = msg["chat"]["id"]
            allowed = CONFIG.allowed_chat_id
            if allowed and str(chat_id) != str(allowed):
                logger.info("Ignored message from chat_id=%s (add to allowed_chat_id in secrets.json to allow)", chat_id)
                continue
            text = (msg.get("text") or "").strip()
            if text:
                _send_typing(chat_id)
                reply = ai_ask(text)
                _send_reply(chat_id, reply)
    except Exception as e:
        logger.debug("Bot poll error: %s", e)


def run_bot_polling():
    logger.info("Bot polling started")
    while True:
        poll_once()
        time.sleep(2)


def start_bot():
    if not CONFIG.telegram_bot_token:
        logger.info("Telegram bot not configured, skipping bot polling")
        return
    t = threading.Thread(target=run_bot_polling, daemon=True)
    t.start()
    logger.info("Bot polling thread started")
