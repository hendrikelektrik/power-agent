import pandas as pd
import numpy as np
from typing import Dict, Any
from datetime import datetime, timedelta
from prophet import Prophet
from power_agent.storage import get_history, pivot_history


def _fallback_prediction(series: pd.DataFrame, hours_ahead: int) -> Dict[str, Any]:
    last_val = series["y"].iloc[-1]
    mean_val = series["y"].mean()
    std_val = series["y"].std()
    now = datetime.now()
    predictions = []
    for h in range(hours_ahead):
        ts = now + timedelta(hours=h)
        jitter = float(np.random.normal(0, std_val * 0.1))
        pred = round(float(mean_val + jitter), 2)
        predictions.append({
            "timestamp": ts.isoformat(timespec="seconds"),
            "predicted_kw": max(pred, 0),
            "lower_kw": max(round(float(mean_val - std_val), 2), 0),
            "upper_kw": round(float(mean_val + std_val), 2),
        })
    peak = max(predictions, key=lambda p: p["predicted_kw"])
    total = sum(p["predicted_kw"] for p in predictions)
    return {
        "plant_id": "",
        "variable": "KW_TOTAL",
        "generated_at": now.isoformat(timespec="seconds"),
        "forecast_hours": hours_ahead,
        "predictions": predictions,
        "summary": {
            "peak_kw": peak["predicted_kw"],
            "peak_at": peak["timestamp"],
            "total_energy_kwh": round(total, 2),
            "avg_kw": round(total / len(predictions), 2),
        },
        "method": "fallback",
    }


def predict_consumption(
    plant_id: str = "mmBanjaran",
    hours_ahead: int = 24,
    variable: str = "KW_TOTAL",
) -> Dict[str, Any]:
    df = get_history(plant_id, limit=2000)
    if df.empty:
        return {"error": "No historical data available"}
    pivoted = pivot_history(df)
    if variable not in pivoted.columns:
        available = [c for c in pivoted.columns if c.startswith("KW_")]
        if not available:
            return {"error": f"Variable {variable} not found, no KW_ variables either"}
        variable = available[0]
    series = pivoted[[variable]].dropna().reset_index()
    series.columns = ["ds", "y"]
    series["ds"] = series["ds"].dt.tz_localize(None) if series["ds"].dt.tz is not None else series["ds"]
    if len(series) < 10:
        return {"error": f"Not enough data points ({len(series)}), need at least 10"}

    if len(series) < 50:
        return _fallback_prediction(series, hours_ahead)

    observed_max = series["y"].max()
    observed_min = series["y"].min()
    range_pad = (observed_max - observed_min) * 2

    model = Prophet(
        yearly_seasonality=False,
        weekly_seasonality=True,
        daily_seasonality=True,
        changepoint_prior_scale=0.05,
    )
    model.add_seasonality(name="hourly", period=1, fourier_order=3)
    model.fit(series)
    future = model.make_future_dataframe(periods=hours_ahead, freq="h", include_history=False)
    forecast = model.predict(future)
    forecast["ds"] = forecast["ds"].dt.tz_localize(None)
    predictions = []
    for _, row in forecast.iterrows():
        raw = row["yhat"]
        capped = min(max(raw, 0), observed_max + range_pad)
        lower = min(max(row["yhat_lower"], 0), observed_max + range_pad)
        upper = min(max(row["yhat_upper"], 0), observed_max + range_pad)
        predictions.append({
            "timestamp": row["ds"].isoformat(),
            "predicted_kw": round(float(capped), 2),
            "lower_kw": round(float(lower), 2),
            "upper_kw": round(float(upper), 2),
        })
    now = datetime.now()
    peak = max(predictions, key=lambda p: p["predicted_kw"])
    total_energy_kwh = sum(p["predicted_kw"] for p in predictions)
    result = {
        "plant_id": plant_id,
        "variable": variable,
        "generated_at": now.isoformat(timespec="seconds"),
        "forecast_hours": hours_ahead,
        "predictions": predictions,
        "summary": {
            "peak_kw": peak["predicted_kw"],
            "peak_at": peak["timestamp"],
            "total_energy_kwh": round(total_energy_kwh, 2),
            "avg_kw": round(total_energy_kwh / len(predictions), 2) if predictions else 0,
        },
        "method": "prophet",
    }
    return result
