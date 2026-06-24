import logging
import threading
import time
from datetime import datetime
import requests
from power_agent.config import CONFIG
from power_agent.storage import get_recent_snapshots
from power_agent.detector import detect_anomalies_zscore
from power_agent.predictor import predict_consumption
from power_agent.analyzer import get_summary
from power_agent.collector import send_daily_summary

logger = logging.getLogger(__name__)

_last_update_id = 0


def _send_reply(chat_id: int, text: str):
    token = CONFIG.telegram_bot_token
    if not token:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=10)
    except Exception as e:
        logger.error("Failed to send bot reply: %s", e)


def _handle_command(chat_id: int, cmd: str):
    cmd = cmd.lower().strip()

    if cmd == "/start":
        _send_reply(chat_id,
            "🤖 <b>DMC Power Agent</b>\n\n"
            "Commands:\n"
            "/status — current live readings\n"
            "/anomalies — latest anomalies\n"
            "/predict — 24h forecast\n"
            "/summary — trigger daily summary")
        return

    if cmd == "/status":
        try:
            snaps = get_recent_snapshots("mmBanjaran", n=1)
            if not snaps:
                _send_reply(chat_id, "No data yet")
                return
            s = snaps[0]
            data = s.get("data", {})
            total = data.get("KW_TOTAL", 0)
            lines = [f"📊 <b>Live Status</b>", f"Time: {s['timestamp'][:19]}", f"Total: {total} kW"]
            for key in ("KW_TOTAL_SPINNING5", "KW_TOTAL_SPINNING6", "KW_TOTAL_COMPRESSOR", "KW_TOTAL_WEAVING"):
                if key in data:
                    label = key.replace("KW_TOTAL_", "").replace("_", " ")
                    lines.append(f"  {label}: {data[key]} kW")
            _send_reply(chat_id, "\n".join(lines))
        except Exception as e:
            _send_reply(chat_id, f"Error: {e}")
        return

    if cmd == "/anomalies":
        try:
            anomalies = detect_anomalies_zscore("mmBanjaran")
            if not anomalies:
                _send_reply(chat_id, "✅ No anomalies detected")
                return
            high = [a for a in anomalies if a["severity"] == "high"]
            lines = [f"⚠️ <b>Anomalies ({len(anomalies)} total, {len(high)} high)</b>"]
            for a in anomalies[:5]:
                t = a["timestamp"][11:19]
                lines.append(f"  • {t} | {a['variable']} = {a['value']} kW | z={a['z_score']}")
            _send_reply(chat_id, "\n".join(lines))
        except Exception as e:
            _send_reply(chat_id, f"Error: {e}")
        return

    if cmd == "/predict":
        try:
            result = predict_consumption("mmBanjaran", hours_ahead=24, variable="KW_TOTAL")
            if "error" in result:
                _send_reply(chat_id, f"Error: {result['error']}")
                return
            s = result.get("summary", {})
            lines = [
                f"📈 <b>24h Forecast</b>",
                f"Method: {result.get('method', 'prophet')}",
                f"Peak: {s.get('peak_kw', '--')} kW at {s.get('peak_at', '--')[:19]}",
                f"Avg: {s.get('avg_kw', '--')} kW",
                f"Energy: {s.get('total_energy_kwh', '--')} kWh",
            ]
            _send_reply(chat_id, "\n".join(lines))
        except Exception as e:
            _send_reply(chat_id, f"Error: {e}")
        return

    if cmd == "/summary":
        try:
            send_daily_summary("mmBanjaran")
            _send_reply(chat_id, "✅ Daily summary sent to channel")
        except Exception as e:
            _send_reply(chat_id, f"Error: {e}")
        return

    _send_reply(chat_id, f"Unknown command: {cmd}\nTry /start")


def poll_once():
    global _last_update_id
    token = CONFIG.telegram_bot_token
    if not token:
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
            text = (msg.get("text") or "").strip()
            if text.startswith("/"):
                _handle_command(chat_id, text)
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
