import os
from datetime import datetime
from fastapi import FastAPI, Query, Body
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional

from power_agent.analyzer import get_summary, get_trend
from power_agent.detector import detect_anomalies_zscore, detect_anomalies_iqr, check_current_anomaly
from power_agent.predictor import predict_consumption
from power_agent.notifier import send_telegram
from power_agent.storage import get_notifications, get_setting, set_setting
from power_agent.storage import get_history, pivot_history, get_recent_snapshots
from power_agent.fetcher import collect_snapshot
from power_agent.collector import send_daily_summary
from power_agent.config import CONFIG

app = FastAPI(title="Power Agent", version="1.0.0")

static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# --- JSON API ---

@app.get("/api")
def api_root():
    return {
        "service": "Power Consumption AI Agent",
        "plants": list(CONFIG.plants.keys()),
        "capacity_kw": CONFIG.plants["mmBanjaran"].capacity_kw,
        "endpoints": [
            "/api/snapshot/latest",
            "/api/snapshot/now",
            "/api/summary",
            "/api/trend",
            "/api/history",
            "/api/anomalies",
            "/api/anomalies/check",
            "/api/predict",
            "/api/notify/status",
            "/api/notify/history",
            "/api/notify/summary",
            "/api/notify/test",
        ],
    }


@app.get("/api/snapshot/latest")
def latest_snapshot(plant_id: str = Query("mmBanjaran")):
    snaps = get_recent_snapshots(plant_id, n=1)
    if not snaps:
        return {"error": "No data yet"}
    return snaps[0]


@app.get("/api/snapshot/now")
def snapshot_now(plant_id: str = Query("mmBanjaran")):
    try:
        return collect_snapshot(plant_id)
    except Exception as e:
        return {"error": f"SCADA unreachable: {e}", "status": "offline"}


@app.get("/api/summary")
def summary(plant_id: str = Query("mmBanjaran")):
    return get_summary(plant_id)


@app.get("/api/trend")
def trend(plant_id: str = Query("mmBanjaran"), hours: int = Query(1, ge=1, le=24)):
    return get_trend(plant_id, hours)


@app.get("/api/history")
def history(
    plant_id: str = Query("mmBanjaran"),
    variables: Optional[str] = Query(None),
    limit: int = Query(200, le=5000),
):
    var_list = variables.split(",") if variables else None
    if var_list == [""]:
        var_list = None
    df = get_history(plant_id, var_list, limit)
    if df.empty:
        return {"data": []}
    pivoted = pivot_history(df)
    pivoted = pivoted.dropna(how="all")
    if pivoted.empty:
        return {"data": []}
    pivoted.index = pivoted.index.astype(str)
    return {
        "plant_id": plant_id,
        "count": len(pivoted),
        "variables": list(pivoted.columns),
        "data": pivoted.reset_index().to_dict(orient="records"),
    }


@app.get("/api/anomalies")
def anomalies(
    plant_id: str = Query("mmBanjaran"),
    method: str = Query("zscore"),
    threshold: float = Query(2.5),
    iqr_multiplier: float = Query(1.5),
):
    if method == "iqr":
        return {"anomalies": detect_anomalies_iqr(plant_id, multiplier=iqr_multiplier), "method": "iqr"}
    return {"anomalies": detect_anomalies_zscore(plant_id, threshold), "method": "zscore"}


@app.get("/api/anomalies/check")
def anomaly_check(plant_id: str = Query("mmBanjaran"), threshold: Optional[float] = Query(None)):
    return check_current_anomaly(plant_id, threshold=threshold)


@app.get("/api/predict")
def predict(
    plant_id: str = Query("mmBanjaran"),
    hours: int = Query(24, ge=1, le=168),
    variable: str = Query("KW_TOTAL"),
):
    return predict_consumption(plant_id, hours_ahead=hours, variable=variable)


@app.get("/api/notify/status")
def notify_status():
    return {
        "configured": bool(CONFIG.telegram_bot_token and CONFIG.telegram_chat_id),
        "bot_token": bool(CONFIG.telegram_bot_token),
        "chat_id": bool(CONFIG.telegram_chat_id),
    }


@app.get("/api/notify/history")
def notify_history(limit: int = Query(50, ge=1, le=500)):
    return {"history": get_notifications(limit)}


@app.get("/api/notify/summary")
def notify_trigger_summary(plant_id: str = Query("mmBanjaran")):
    send_daily_summary(plant_id)
    return {"status": "sent"}


@app.get("/api/notify/test")
def notify_test():
    ok = send_telegram("✅ <b>DMC Power Agent</b> — Test notification successful")
    if ok:
        return {"status": "sent"}
    return {"status": "failed", "message": "Telegram not configured or request failed"}


# --- Admin Settings ---

_NOTIFY_KEYS = [
    "notify_anomaly_enabled",
    "notify_summary_enabled",
    "notify_scada_offline_enabled",
    "notify_scada_online_enabled",
]


def _load_settings() -> dict:
    result = {}
    result["daily_summary_time"] = get_setting("daily_summary_time", CONFIG.daily_summary_time)
    for key in _NOTIFY_KEYS:
        default = "1" if getattr(CONFIG, key, True) else "0"
        result[key] = get_setting(key, default)
    return result


def _save_setting(key: str, value: str):
    set_setting(key, value)
    if hasattr(CONFIG, key):
        setattr(CONFIG, key, value == "1")


@app.get("/api/admin/settings")
def admin_settings():
    return _load_settings()


@app.post("/api/admin/settings")
def admin_update_settings(body: dict = Body(...)):
    if "daily_summary_time" in body:
        val = body["daily_summary_time"]
        set_setting("daily_summary_time", val)
        CONFIG.daily_summary_time = val
    for key in _NOTIFY_KEYS:
        if key in body:
            _save_setting(key, body[key])
    return {"ok": True, **_load_settings()}


# --- Admin Auth ---

@app.get("/api/admin/status")
def admin_status():
    return {"password_set": bool(CONFIG.admin_password)}


@app.post("/api/admin/login")
def admin_login(password: str = Body(..., embed=True)):
    if not CONFIG.admin_password:
        return {"ok": True}
    if password == CONFIG.admin_password:
        return {"ok": True}
    return JSONResponse(status_code=403, content={"ok": False, "message": "Invalid password"})


# --- UI ---

@app.get("/")
def index():
    return RedirectResponse(url="/static/dashboard.html")
