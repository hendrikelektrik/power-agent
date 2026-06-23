import os
import sqlite3
import pandas as pd
from typing import Dict, Optional, List
from power_agent.config import CONFIG


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(CONFIG.db_path), exist_ok=True)
    conn = sqlite3.connect(CONFIG.db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            plant_id TEXT NOT NULL,
            plant_name TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            variable TEXT NOT NULL,
            value REAL NOT NULL,
            FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_snapshots_plant_time
        ON snapshots(plant_id, timestamp)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_readings_variable
        ON readings(variable)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            kind TEXT NOT NULL,
            message TEXT NOT NULL,
            success INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def save_snapshot(snapshot: Dict) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO snapshots (timestamp, plant_id, plant_name) VALUES (?, ?, ?)",
        (snapshot["timestamp"], snapshot["plant_id"], snapshot["plant_name"]),
    )
    snapshot_id = cur.lastrowid
    data = snapshot.get("data", {})
    rows = [(snapshot_id, k, v) for k, v in data.items()]
    conn.executemany(
        "INSERT INTO readings (snapshot_id, variable, value) VALUES (?, ?, ?)", rows
    )
    conn.commit()
    conn.close()
    return snapshot_id


def get_history(
    plant_id: str = "mmBanjaran",
    variables: Optional[List[str]] = None,
    limit: int = 1000,
) -> pd.DataFrame:
    conn = get_connection()
    if variables:
        placeholders = ",".join("?" * len(variables))
        query = f"""
            SELECT s.timestamp, s.plant_id, r.variable, r.value
            FROM snapshots s
            JOIN readings r ON r.snapshot_id = s.id
            WHERE s.plant_id = ? AND r.variable IN ({placeholders})
            ORDER BY s.timestamp DESC
            LIMIT ?
        """
        params = [plant_id] + variables + [limit]
    else:
        query = """
            SELECT s.timestamp, s.plant_id, r.variable, r.value
            FROM snapshots s
            JOIN readings r ON r.snapshot_id = s.id
            WHERE s.plant_id = ?
            ORDER BY s.timestamp DESC
            LIMIT ?
        """
        params = [plant_id, limit]
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def pivot_history(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    pivoted = df.pivot_table(
        index="timestamp", columns="variable", values="value", aggfunc="first"
    ).sort_index()
    pivoted = pivoted.ffill().bfill().dropna(how="all")
    return pivoted


def get_recent_snapshots(plant_id: str = "mmBanjaran", n: int = 5) -> List[Dict]:
    conn = get_connection()
    cur = conn.execute(
        "SELECT id, timestamp, plant_id, plant_name FROM snapshots WHERE plant_id = ? ORDER BY timestamp DESC LIMIT ?",
        (plant_id, n),
    )
    snapshots = []
    for row in cur.fetchall():
        snap_id = row[0]
        rcur = conn.execute(
            "SELECT variable, value FROM readings WHERE snapshot_id = ?", (snap_id,)
        )
        data = {r[0]: r[1] for r in rcur.fetchall()}
        snapshots.append({
            "timestamp": row[1],
            "plant_id": row[2],
            "plant_name": row[3],
            "data": data,
        })
    conn.close()
    return snapshots


def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    cur = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key: str, value: str):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
    conn.close()


def save_notification(kind: str, message: str, success: bool):
    conn = get_connection()
    from datetime import datetime
    conn.execute(
        "INSERT INTO notifications (timestamp, kind, message, success) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(), kind, message, 1 if success else 0),
    )
    conn.commit()
    conn.close()


def get_notifications(limit: int = 50) -> list:
    conn = get_connection()
    cur = conn.execute(
        "SELECT timestamp, kind, message, success FROM notifications ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = [
        {
            "timestamp": r[0],
            "kind": r[1],
            "message": r[2],
            "success": bool(r[3]),
        }
        for r in cur.fetchall()
    ]
    conn.close()
    return rows
