# DMC Power Agent

Industrial power consumption monitoring, anomaly detection, and forecasting system.

## Quick Start

```bash
git clone <repo>
cd boring5
python -m venv .venv
# activate venv
pip install -r requirements.txt
cp power_agent/secrets.example.json power_agent/secrets.json
# edit secrets.json with your bot token, chat ID, password, SCADA URL
python -m power_agent all       # collector + API server
python -m power_agent api       # API only (port 8765)
python -m power_agent collect   # collector only
```

## Features

- **Live Dashboard** — real-time power monitoring with section breakdowns
- **Anomaly Detection** — z-score based with configurable threshold
- **Forecasting** — Prophet + statistical fallback (up to 168h)
- **Telegram Alerts** — anomaly alerts, SCADA offline/restored, daily summary
- **Admin Panel** — password-protected, toggle notifications, set summary time

## API Endpoints

All under `/api`: `summary`, `trend`, `history`, `anomalies`, `anomalies/check`, `predict`, `snapshot/latest`, `snapshot/now`, `notify/status`, `notify/history`, `notify/summary`, `notify/test`, `admin/settings`, `admin/login`

## Security

- Secrets in `secrets.json` (gitignored)
- Admin page password-protected (server-side)
- Telegram via bot token (server-side only)
