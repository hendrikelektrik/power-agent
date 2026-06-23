import logging
from typing import Optional
import requests
from power_agent.config import CONFIG
from power_agent.storage import save_notification, get_notifications

logger = logging.getLogger(__name__)


def _send_to(chat_id: str, message: str) -> bool:
    token = CONFIG.telegram_bot_token
    if not token:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id.strip(),
            "text": message,
            "parse_mode": "HTML",
        }, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        body = getattr(e, "response", None)
        detail = body.text if body is not None else str(e)
        logger.error("Failed to send Telegram to %s: %s", chat_id, detail)
        return False


def send_telegram(message: str, kind: str = "manual") -> bool:
    raw = CONFIG.telegram_chat_id
    if not CONFIG.telegram_bot_token or not raw:
        logger.debug("Telegram not configured, skipping notification")
        save_notification(kind, message, False)
        return False
    ids = [c.strip() for c in raw.split(",") if c.strip()]
    ok = True
    for cid in ids:
        if not _send_to(cid, message):
            ok = False
    save_notification(kind, message, ok)
    if ok:
        logger.info("Telegram sent to %d recipient(s)", len(ids))
    return ok


def notify_anomaly(plant_name: str, anomaly_count: int, top: list) -> bool:
    lines = [
        f"⚠️ <b>DMC Power Agent — Anomaly Alert</b>",
        f"Plant: {plant_name}",
        f"Anomalies detected: {anomaly_count}",
    ]
    for a in top[:5]:
        t = a["timestamp"][11:19]
        lines.append(f"  • {t} | {a['variable']} = {a['value']} kW | z={a['z_score']}")
    return send_telegram("\n".join(lines), kind="anomaly")
