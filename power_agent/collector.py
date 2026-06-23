import time
import logging
from datetime import datetime, timedelta
import schedule
from power_agent.fetcher import collect_snapshot
from power_agent.storage import save_snapshot, init_db, get_history, pivot_history, get_setting
from power_agent.detector import detect_anomalies_zscore
from power_agent.notifier import notify_anomaly, send_telegram
from power_agent.config import CONFIG

logger = logging.getLogger(__name__)

_last_scada_offline_notified: float = 0
_was_scada_offline: bool = False


def send_daily_summary(plant_id: str = "mmBanjaran"):
    if not CONFIG.notify_summary_enabled:
        logger.debug("Daily summary disabled by config")
        return
    try:
        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        df = get_history(plant_id, limit=5000)
        if df.empty:
            logger.debug("No data for daily summary")
            return
        recent = df[df["timestamp"] >= cutoff]
        if recent.empty:
            logger.debug("No data in last 24h for daily summary")
            return
        pivoted = pivot_history(recent)
        if "KW_TOTAL" not in pivoted.columns:
            return
        vals = pivoted["KW_TOTAL"].dropna()
        if vals.empty:
            return
        min_kw = round(float(vals.min()), 2)
        avg_kw = round(float(vals.mean()), 2)
        max_kw = round(float(vals.max()), 2)
        # energy in kWh: avg kW * hours (assuming ~1 reading per minute)
        hours = len(vals) / 60.0
        energy = round(avg_kw * hours, 2) if hours > 0 else 0
        peak_idx = vals.idxmax()
        peak_time = peak_idx.strftime("%H:%M") if hasattr(peak_idx, "strftime") else str(peak_idx)[11:16]
        anomalies = detect_anomalies_zscore(plant_id)
        anomaly_count = len([a for a in anomalies if a["severity"] == "high"])
        lines = [
            f"📊 <b>DMC Power Agent — Daily Summary</b>",
            f"Date: {datetime.now().strftime('%Y-%m-%d')}",
            "",
            f"⚡ <b>Power Consumption (24h)</b>",
            f"  Min: {min_kw} kW",
            f"  Avg: {avg_kw} kW",
            f"  Max: {max_kw} kW",
            f"  Energy: {energy} kWh",
            f"  Peak at: {peak_time}",
        ]
        if anomaly_count:
            lines.append(f"")
            lines.append(f"⚠️ High-severity anomalies: {anomaly_count}")
        send_telegram("\n".join(lines), kind="summary")
        logger.info("Daily summary sent")
    except Exception as e:
        logger.error("Failed to send daily summary: %s", e)


def collect_and_store(plant_id: str = "mmBanjaran"):
    global _last_scada_offline_notified, _was_scada_offline
    try:
        snapshot = collect_snapshot(plant_id)
    except Exception as e:
        logger.error("Failed to collect data for %s: %s", plant_id, e)
        # SCADA offline alert (rate-limited to once per hour)
        now = time.time()
        if CONFIG.notify_scada_offline_enabled and now - _last_scada_offline_notified > 3600:
            _last_scada_offline_notified = now
            _was_scada_offline = True
            send_telegram(
                f"🔴 <b>DMC Power Agent — SCADA Offline</b>\n"
                f"Plant: {plant_id}\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                kind="scada_offline",
            )
        return
    # SCADA recovered
    if _was_scada_offline:
        _was_scada_offline = False
        _last_scada_offline_notified = 0
        if CONFIG.notify_scada_online_enabled:
            send_telegram(
                f"🟢 <b>DMC Power Agent — SCADA Restored</b>\n"
                f"Plant: {plant_id}\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                kind="scada_online",
            )
    try:
        snap_id = save_snapshot(snapshot)
        total = snapshot["data"].get("KW_TOTAL", 0)
        logger.info(
            "Saved snapshot #%d for %s | Total: %.2f kW | %d variables",
            snap_id,
            plant_id,
            total,
            len(snapshot["data"]),
        )
        if CONFIG.notify_anomaly_enabled:
            anomalies = detect_anomalies_zscore(plant_id)
            high = [a for a in anomalies if a["severity"] == "high"]
            if high:
                plant_name = snapshot.get("plant_name", plant_id)
                notify_anomaly(plant_name, len(high), high[:5])
    except Exception as e:
        logger.error("Error processing data for %s: %s", plant_id, e)


def run_collector_loop(interval_seconds: int = 60):
    init_db()
    logger.info("Starting data collector every %d seconds", interval_seconds)
    collect_and_store()
    schedule.every(interval_seconds).seconds.do(collect_and_store)
    # daily summary at configured time (from DB, fallback to config)
    summary_time = get_setting("daily_summary_time", CONFIG.daily_summary_time)
    schedule.every().day.at(summary_time).do(send_daily_summary)
    logger.info("Daily summary scheduled at %s", summary_time)
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Collector stopped by user")
