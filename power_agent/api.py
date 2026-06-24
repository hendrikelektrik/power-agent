import os
from datetime import datetime, timedelta
import pandas as pd
import requests
from fastapi import FastAPI, Query, Body
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
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
from power_agent.bot import start_bot
from power_agent.config import CONFIG

app = FastAPI(title="Power Agent", version="1.0.0")

static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@app.get("/favicon.ico")
def favicon():
    return FileResponse(os.path.join(STATIC_DIR, "favicon.svg"), media_type="image/svg+xml")


@app.on_event("startup")
def _start_bot():
    start_bot()


@app.get("/api/bot/info")
def bot_info():
    token = CONFIG.telegram_bot_token
    if not token:
        return {"configured": False}
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        if r.ok:
            data = r.json().get("result", {})
            return {
                "configured": True,
                "username": data.get("username", "unknown"),
                "name": data.get("first_name", ""),
            }
    except Exception:
        pass
    return {"configured": True, "username": "unknown", "name": ""}


@app.get("/api/bot/test")
def bot_test():
    from power_agent.bot import poll_once
    poll_once()
    return {"status": "ok"}


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


SHIFT_DEFS = [
    {"id": 1, "label": "Shift 1 (07:30-13:30)", "start": "07:30", "end": "13:30", "hours": 6},
    {"id": 2, "label": "Shift 2 (13:30-21:30)", "start": "13:30", "end": "21:30", "hours": 8},
    {"id": 3, "label": "Shift 3 (21:30-07:30)", "start": "21:30", "end": "07:30", "hours": 10},
]


SECTION_LABELS = {
    "KW_TOTAL": "Total",
    "KW_TOTAL_SPINNING5": "Sp 5",
    "KW_TOTAL_SPINNING6": "Sp 6",
    "KW_TOTAL_COMPRESSOR": "Comp",
    "KW_TOTAL_WEAVING": "Weav",
    "KW_TOTAL_PP2G": "PP2G",
}


def _time_to_shift(t):
    h, m = t.hour, t.minute
    if h == 7 and m >= 30 or 8 <= h < 13 or h == 13 and m < 30:
        return 1
    if h == 13 and m >= 30 or 14 <= h < 21 or h == 21 and m < 30:
        return 2
    return 3


def _calc_shifts_for_date(
    date: str,
    tariff_wbp: float = 0,
    tariff_lwbp: float = 0,
    wbp_start: str = "18:00",
    wbp_end: str = "22:00",
) -> list:
    next_day = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    query_start = f"{date}T07:30:00"
    query_end = f"{next_day}T07:30:00"
    df = get_history("mmBanjaran", limit=10000, start_date=query_start, end_date=query_end)
    if df.empty:
        return []
    pivoted = pivot_history(df)
    if pivoted.empty:
        return []
    pivoted = pivoted.sort_index()
    cols = [c for c in pivoted.columns if c.startswith("KW_TOTAL")]
    if not cols:
        return []
    deltas = pivoted.index.to_series().diff().dt.total_seconds().div(3600).fillna(1 / 60)
    sections = [c for c in cols if c in SECTION_LABELS]

    wbp_h = int(wbp_start.split(":")[0])
    wbp_m = int(wbp_start.split(":")[1])
    wbp_end_h = int(wbp_end.split(":")[0])
    wbp_end_m = int(wbp_end.split(":")[1])

    def _is_wbp(t):
        if wbp_end_h > wbp_h or (wbp_end_h == wbp_h and wbp_end_m > wbp_m):
            return (t.hour > wbp_h or (t.hour == wbp_h and t.minute >= wbp_m)) and \
                   (t.hour < wbp_end_h or (t.hour == wbp_end_h and t.minute < wbp_end_m))
        return False

    shifts_data = {1: {}, 2: {}, 3: {}}
    peak_data = {1: {}, 2: {}, 3: {}}
    cost_data = {1: {}, 2: {}, 3: {}}
    for s in sections:
        for sh_id in shifts_data:
            shifts_data[sh_id][s] = 0.0
            peak_data[sh_id][s] = 0.0
            cost_data[sh_id][s] = 0.0
    for i in range(len(pivoted)):
        ts = pivoted.index[i]
        sh = _time_to_shift(ts)
        dt = deltas.iloc[i]
        rate = tariff_wbp if _is_wbp(ts) else tariff_lwbp
        for s in sections:
            v = pivoted[s].iloc[i]
            if pd.notna(v):
                kwh = v * dt
                shifts_data[sh][s] += kwh
                cost_data[sh][s] += kwh * rate
                if v > peak_data[sh][s]:
                    peak_data[sh][s] = v
    total_kwh = {1: 0.0, 2: 0.0, 3: 0.0}
    total_peak = {1: 0.0, 2: 0.0, 3: 0.0}
    total_cost = {1: 0.0, 2: 0.0, 3: 0.0}
    for sh_id in shifts_data:
        for s in shifts_data[sh_id]:
            shifts_data[sh_id][s] = round(shifts_data[sh_id][s], 2)
            total_kwh[sh_id] += shifts_data[sh_id][s]
            peak_data[sh_id][s] = round(peak_data[sh_id][s], 2)
            if peak_data[sh_id][s] > total_peak[sh_id]:
                total_peak[sh_id] = peak_data[sh_id][s]
            cost_data[sh_id][s] = round(cost_data[sh_id][s], 2)
            total_cost[sh_id] += cost_data[sh_id][s]
        total_kwh[sh_id] = round(total_kwh[sh_id], 2)
        total_peak[sh_id] = round(total_peak[sh_id], 2)
        total_cost[sh_id] = round(total_cost[sh_id], 2)
    results = []
    for sd in SHIFT_DEFS:
        sid = sd["id"]
        sections_out = {}
        peaks_out = {}
        costs_out = {}
        for s in sections:
            label = SECTION_LABELS.get(s, s)
            sections_out[label] = shifts_data[sid][s]
            peaks_out[label] = peak_data[sid][s]
            costs_out[label] = cost_data[sid][s]
        results.append({
            "id": sid,
            "label": sd["label"],
            "hours": sd["hours"],
            "total_kwh": total_kwh[sid],
            "kwh_per_hour": round(total_kwh[sid] / sd["hours"], 2),
            "peak_kw": total_peak[sid],
            "total_cost": total_cost[sid],
            "sections": sections_out,
            "peak_sections": peaks_out,
            "cost_sections": costs_out,
        })
    return results


@app.get("/api/energy/debug")
def energy_debug(date: str = Query(None)):
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    next_day = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    query_start = f"{date}T07:30:00"
    query_end = f"{next_day}T07:30:00"
    df = get_history("mmBanjaran", limit=10000, start_date=query_start, end_date=query_end)
    rows = []
    if not df.empty:
        pivoted = pivot_history(df).sort_index()
        for i in range(min(len(pivoted), 100)):
            ts = pivoted.index[i]
            sh = _time_to_shift(ts)
            rows.append({"ts": str(ts), "hour": ts.hour, "minute": ts.minute, "shift": sh})
    sh_counts = {1: 0, 2: 0, 3: 0}
    for r in rows:
        sh_counts[r["shift"]] += 1
    first_ts = str(pivoted.index[0]) if not pivoted.empty else "N/A"
    last_ts = str(pivoted.index[-1]) if not pivoted.empty else "N/A"
    return {
        "date": date,
        "query_start": query_start,
        "query_end": query_end,
        "data_points": len(rows),
        "shift_counts": sh_counts,
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
        "samples": rows,
    }


@app.get("/api/energy")
def energy(date: str = Query(None)):
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    tw = float(get_setting("tariff_wbp", CONFIG.tariff_wbp))
    tl = float(get_setting("tariff_lwbp", CONFIG.tariff_lwbp))
    ws = get_setting("wbp_start", CONFIG.wbp_start)
    we = get_setting("wbp_end", CONFIG.wbp_end)
    shifts = _calc_shifts_for_date(date, tariff_wbp=tw, tariff_lwbp=tl, wbp_start=ws, wbp_end=we)
    week_ago = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    prev_shifts = _calc_shifts_for_date(week_ago, tariff_wbp=tw, tariff_lwbp=tl, wbp_start=ws, wbp_end=we)

    prev_lookup = {}
    for ps in prev_shifts:
        prev_lookup[ps["id"]] = ps["total_kwh"]

    for sh in shifts:
        prev_kwh = prev_lookup.get(sh["id"])
        if prev_kwh and prev_kwh > 0:
            sh["vs_last_week_pct"] = round((sh["total_kwh"] - prev_kwh) / prev_kwh * 100, 1)
            sh["vs_last_week_kwh"] = round(sh["total_kwh"] - prev_kwh, 2)
            sh["last_week_kwh"] = prev_kwh
        else:
            sh["vs_last_week_pct"] = None
            sh["vs_last_week_kwh"] = None
            sh["last_week_kwh"] = None

    return {"date": date, "shifts": shifts, "show_cost": get_setting("show_cost", CONFIG.show_cost) == "1"}


@app.get("/api/energy/trend")
def energy_trend(days: int = Query(30, ge=7, le=90)):
    today = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    df = get_history("mmBanjaran", limit=50000, start_date=start, end_date=f"{today}T23:59:59")
    if df.empty:
        return {"days": days, "daily": []}

    pivoted = pivot_history(df)
    if pivoted.empty:
        return {"days": days, "daily": []}

    pivoted = pivoted.sort_index()
    total_col = [c for c in pivoted.columns if c == "KW_TOTAL"]
    if not total_col:
        return {"days": days, "daily": []}
    total_col = total_col[0]

    deltas = pivoted.index.to_series().diff().dt.total_seconds().div(3600).fillna(1 / 60)
    wh = pivoted[total_col] * deltas
    wh.name = "kwh"

    daily = wh.resample("D").sum().reset_index()
    daily.columns = ["date", "kwh"]
    daily["kwh"] = daily["kwh"].round(2)

    return {
        "days": days,
        "daily": daily.to_dict(orient="records"),
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
def notify_history(
    limit: int = Query(50, ge=1, le=500),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    from power_agent.storage import count_notifications as cnt
    return {
        "history": get_notifications(limit, start_date=start_date, end_date=end_date),
        "total": cnt(start_date=start_date, end_date=end_date),
    }


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


_TARIFF_KEYS = ["tariff_wbp", "tariff_lwbp", "wbp_start", "wbp_end", "show_cost"]


def _load_settings() -> dict:
    result = {}
    result["daily_summary_time"] = get_setting("daily_summary_time", CONFIG.daily_summary_time)
    for key in _NOTIFY_KEYS:
        default = "1" if getattr(CONFIG, key, True) else "0"
        result[key] = get_setting(key, default)
    for key in _TARIFF_KEYS:
        result[key] = get_setting(key, getattr(CONFIG, key, ""))
    return result


def _save_setting(key: str, value: str):
    set_setting(key, value)
    if hasattr(CONFIG, key):
        if key in _NOTIFY_KEYS:
            setattr(CONFIG, key, value == "1")
        else:
            setattr(CONFIG, key, value)


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
    for key in _TARIFF_KEYS:
        if key in body:
            _save_setting(key, str(body[key]))
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
