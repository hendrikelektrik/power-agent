import json
import os
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class PlantConfig:
    name: str
    scada_id: str
    scada_url: str
    capacity_kw: float = 10000


@dataclass
class AppConfig:
    fetch_interval_seconds: int = 60
    db_path: str = "power_agent/data/history.db"
    api_host: str = "0.0.0.0"
    api_port: int = 8765

    plants: Dict[str, PlantConfig] = field(default_factory=lambda: {
        "mmBanjaran": PlantConfig(
            name="Banjaran Plant",
            scada_id="mmBanjaran",
            scada_url="http://<scada-ip>/services/html5Api/scadaState.json?id=mmBanjaran",
        ),
    })

    anomaly_zscore_threshold: float = 2.5

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    admin_password: str = ""

    daily_summary_time: str = "07:00"

    # notification toggles (overridden by DB settings at runtime)
    notify_anomaly_enabled: bool = True
    notify_summary_enabled: bool = True
    notify_scada_offline_enabled: bool = True
    notify_scada_online_enabled: bool = True

    # tariff
    tariff_wbp: str = "1035.78"
    tariff_lwbp: str = "1035.78"
    wbp_start: str = "18:00"
    wbp_end: str = "22:00"
    show_cost: str = "0"


CONFIG = AppConfig()

# Load secrets from secrets.json (gitignored) if it exists
_secrets_path = os.path.join(os.path.dirname(__file__), "secrets.json")
if os.path.exists(_secrets_path):
    try:
        with open(_secrets_path) as f:
            secrets = json.load(f)
        for key in ("telegram_bot_token", "telegram_chat_id", "admin_password"):
            if key in secrets:
                setattr(CONFIG, key, secrets[key])
        if "plants" in secrets:
            for pid, overrides in secrets["plants"].items():
                if pid in CONFIG.plants:
                    for k, v in overrides.items():
                        setattr(CONFIG.plants[pid], k, v)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Failed to load secrets.json: %s", e)
