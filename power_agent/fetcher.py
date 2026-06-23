import requests
from typing import Dict, Any
from datetime import datetime
from power_agent.config import CONFIG


def fetch_scada_state(plant_id: str) -> Dict[str, Any]:
    plant = CONFIG.plants[plant_id]
    resp = requests.get(plant.scada_url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def parse_scada_data(raw: Dict[str, Any]) -> Dict[str, float]:
    state = raw.get("scadaState", {})
    control_list = state.get("control", [])
    result = {}
    for ctrl in control_list:
        val = ctrl.get("value")
        if val is not None:
            try:
                result["KW_TOTAL"] = round(float(val), 2)
            except (ValueError, TypeError):
                pass
        variables = ctrl.get("variable", [])
        if isinstance(variables, dict):
            variables = [variables]
        for var in variables:
            vid = var.get("id", "")
            vval = var.get("value", "0")
            short_name = vid.split(".")[-1] if "." in vid else vid
            try:
                result[short_name] = round(float(vval), 2)
            except (ValueError, TypeError):
                pass
    return result


def collect_snapshot(plant_id: str = "mmBanjaran") -> Dict[str, Any]:
    raw = fetch_scada_state(plant_id)
    data = parse_scada_data(raw)
    snapshot = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "plant_id": plant_id,
        "plant_name": CONFIG.plants[plant_id].name,
        "data": data,
    }
    return snapshot
