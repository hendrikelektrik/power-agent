import pandas as pd
import numpy as np
from typing import Dict, Any
from datetime import datetime, timedelta
from power_agent.storage import get_history, pivot_history


def get_latest_readings(plant_id: str = "mmBanjaran") -> Dict[str, float]:
    df = get_history(plant_id, limit=1)
    if df.empty:
        return {}
    latest = df[df["timestamp"] == df["timestamp"].max()]
    return dict(zip(latest["variable"], latest["value"]))


def get_summary(plant_id: str = "mmBanjaran") -> Dict[str, Any]:
    df = get_history(plant_id, limit=200)
    if df.empty:
        return {"error": "No data available"}
    pivoted = pivot_history(df)
    total_col = "KW_TOTAL"
    summary_vars = [
        "KW_TOTAL",
        "KW_TOTAL_COMPRESSOR",
        "KW_TOTAL_WEAVING",
        "KW_TOTAL_SPINNING5",
        "KW_TOTAL_SPINNING6",
        "KW_TOTAL_PP2G",
    ]
    summary = {
        "plant_id": plant_id,
        "current": {},
        "avg": {},
        "min": {},
        "max": {},
        "std": {},
    }
    for col in pivoted.columns:
        if col in summary_vars or col.startswith("KW_"):
            vals = pivoted[col].dropna()
            if not vals.empty:
                summary["current"][col] = round(float(vals.iloc[-1]), 2)
                summary["avg"][col] = round(float(vals.mean()), 2)
                summary["min"][col] = round(float(vals.min()), 2)
                summary["max"][col] = round(float(vals.max()), 2)
                summary["std"][col] = round(float(vals.std()), 2)
    return summary


def get_trend(plant_id: str = "mmBanjaran", hours: int = 1) -> Dict[str, float]:
    df = get_history(plant_id, limit=500)
    if df.empty:
        return {}
    pivoted = pivot_history(df)
    if "KW_TOTAL" not in pivoted.columns:
        return {}
    cutoff = datetime.now() - timedelta(hours=hours)
    recent = pivoted[pivoted.index >= cutoff]
    if len(recent) < 2:
        return {"trend_kw_per_hour": 0.0, "direction": "stable"}
    vals = recent["KW_TOTAL"].values
    x = np.arange(len(vals))
    slope = np.polyfit(x, vals, 1)[0]
    change_per_hour = round(slope * (len(vals) / max(hours, 1)), 2)
    direction = "up" if change_per_hour > 5 else ("down" if change_per_hour < -5 else "stable")
    return {
        "trend_kw_per_hour": change_per_hour,
        "direction": direction,
        "current_kw": round(float(vals[-1]), 2),
        "avg_kw": round(float(vals.mean()), 2),
    }
