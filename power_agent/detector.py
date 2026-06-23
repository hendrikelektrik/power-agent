import numpy as np
from typing import Dict, Any, List, Optional
from datetime import datetime
from power_agent.config import CONFIG
from power_agent.storage import get_history, pivot_history


def detect_anomalies_zscore(
    plant_id: str = "mmBanjaran",
    threshold: Optional[float] = None,
) -> List[Dict[str, Any]]:
    if threshold is None:
        threshold = CONFIG.anomaly_zscore_threshold
    df = get_history(plant_id, limit=500)
    if df.empty:
        return []
    pivoted = pivot_history(df)
    anomalies = []
    total_cols = [c for c in pivoted.columns if c.startswith("KW_TOTAL")]
    target_cols = total_cols if total_cols else [pivoted.columns[0]]
    for col in target_cols:
        if col not in pivoted.columns:
            continue
        vals = pivoted[col].dropna().values
        if len(vals) < 10:
            continue
        mean = np.mean(vals)
        std = np.std(vals)
        if std == 0:
            continue
        z_scores = np.abs((vals - mean) / std)
        anomaly_indices = np.where(z_scores > threshold)[0]
        for idx in anomaly_indices:
            anomalies.append({
                "timestamp": pivoted.index[idx].isoformat(),
                "variable": col,
                "value": round(float(vals[idx]), 2),
                "mean": round(float(mean), 2),
                "std": round(float(std), 2),
                "z_score": round(float(z_scores[idx]), 2),
                "severity": "high" if z_scores[idx] > 3.0 else "medium",
            })
    return sorted(anomalies, key=lambda a: a["timestamp"], reverse=True)


def detect_anomalies_iqr(
    plant_id: str = "mmBanjaran",
    multiplier: float = 1.5,
) -> List[Dict[str, Any]]:
    df = get_history(plant_id, limit=500)
    if df.empty:
        return []
    pivoted = pivot_history(df)
    anomalies = []
    target_cols = [c for c in pivoted.columns if c.startswith("KW_TOTAL")]
    target_cols = target_cols if target_cols else [pivoted.columns[0]]
    for col in target_cols:
        if col not in pivoted.columns:
            continue
        vals = pivoted[col].dropna().values
        if len(vals) < 10:
            continue
        q1, q3 = np.percentile(vals, 25), np.percentile(vals, 75)
        iqr = q3 - q1
        lower = q1 - multiplier * iqr
        upper = q3 + multiplier * iqr
        for i, v in enumerate(vals):
            if v < lower or v > upper:
                anomalies.append({
                    "timestamp": pivoted.index[i].isoformat(),
                    "variable": col,
                    "value": round(float(v), 2),
                    "lower_bound": round(float(lower), 2),
                    "upper_bound": round(float(upper), 2),
                    "method": "iqr",
                })
    return sorted(anomalies, key=lambda a: a["timestamp"], reverse=True)


def check_current_anomaly(
    plant_id: str = "mmBanjaran",
    threshold: Optional[float] = None,
) -> Dict[str, Any]:
    if threshold is None:
        threshold = CONFIG.anomaly_zscore_threshold
    anomalies = detect_anomalies_zscore(plant_id, threshold=threshold)
    current_time = datetime.now().isoformat(timespec="seconds")
    recent = [a for a in anomalies if a["timestamp"].startswith(current_time[:10])]
    if not recent:
        return {
            "status": "normal",
            "message": "No anomalies detected in recent readings",
            "anomalies": [],
        }
    return {
        "status": "anomaly_detected",
        "message": f"Found {len(recent)} anomalous readings",
        "anomalies": recent[:10],
    }
