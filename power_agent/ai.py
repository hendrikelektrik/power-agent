import os
import logging
from google import genai
from datetime import datetime
from power_agent.config import CONFIG
from power_agent.storage import get_setting
from power_agent.analyzer import get_latest_readings, get_summary
from power_agent.detector import detect_anomalies_zscore
from power_agent.predictor import predict_consumption

logger = logging.getLogger(__name__)

def _load_prompt() -> str:
    db_val = get_setting("ai_prompt", "")
    if db_val:
        return db_val
    path = os.path.join(os.path.dirname(__file__), "ai_prompt.md")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    return "You are an industrial power monitoring AI for a textile plant."


def _gather_context() -> str:
    lines = [f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]
    try:
        readings = get_latest_readings()
        if readings:
            parts = ["Live readings (kW):"]
            for k, v in readings.items():
                label = k.replace("KW_TOTAL_", "").replace("_", " ")
                parts.append(f"  {label}: {v}")
            lines.append("\n".join(parts))
    except Exception as e:
        logger.warning("Failed to get readings: %s", e)
    try:
        summary = get_summary()
        if summary and "current" in summary:
            parts = ["Summary (last 200 readings):"]
            for k in ("KW_TOTAL", "KW_TOTAL_COMPRESSOR", "KW_TOTAL_WEAVING", "KW_TOTAL_SPINNING5", "KW_TOTAL_SPINNING6", "KW_TOTAL_PP2G"):
                if k in summary["current"]:
                    label = k.replace("KW_TOTAL_", "").replace("_", " ")
                    cur = summary["current"][k]
                    avg = summary["avg"][k]
                    parts.append(f"  {label}: current={cur} avg={avg}")
            lines.append("\n".join(parts))
    except Exception as e:
        logger.warning("Failed to get summary: %s", e)
    try:
        anomalies = detect_anomalies_zscore()
        if anomalies:
            a_lines = [f"Latest anomalies ({len(anomalies)}):"]
            for a in anomalies[:3]:
                a_lines.append(f"  {a['timestamp'][:19]} {a['variable']} = {a['value']}kW z={a['z_score']}")
            lines.append("\n".join(a_lines))
        else:
            lines.append("No anomalies detected.")
    except Exception as e:
        logger.warning("Failed to get anomalies: %s", e)
    try:
        pred = predict_consumption("mmBanjaran", hours_ahead=24, variable="KW_TOTAL")
        if "error" not in pred:
            s = pred.get("summary", {})
            lines.append(f"24h forecast: peak {s.get('peak_kw', '--')}kW, avg {s.get('avg_kw', '--')}kW, energy {s.get('total_energy_kwh', '--')}kWh")
    except Exception as e:
        logger.warning("Failed to get prediction: %s", e)
    return "\n".join(lines)


def ask(question: str) -> str:
    key = CONFIG.gemini_api_key
    if not key:
        return "Gemini API key not configured. Add `gemini_api_key` to secrets.json."
    try:
        client = genai.Client(api_key=key)
        context = _gather_context()
        prompt = f"{_load_prompt()}\n\nHere is the current plant data:\n{context}\n\nUser question: {question}"
        resp = client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt)
        return resp.text.strip()
    except Exception as e:
        logger.error("Gemini API error: %s", e)
        return f"AI error: {e}"
