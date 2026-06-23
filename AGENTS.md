# Power Consumption AI Agent — AGENTS.md

## Quick start

```powershell
.venv\Scripts\Activate.ps1
python -m power_agent all       # collector + API server
python -m power_agent api       # API only (port 8765)
python -m power_agent collect   # collector only
```

## Architecture

- **Package:** `power_agent/` — flat layout, no `pyproject.toml` or `setup.py`
- **Entry:** `power_agent/main.py` with argparse (`collect`/`api`/`all`)
- **Framework:** FastAPI (`power_agent/api.py`), SQLite (`power_agent/storage.py`)
- **UI:** Static HTML in `power_agent/static/` served via `StaticFiles` mount
- **DB:** Auto-creates at `power_agent/data/history.db` on first `init_db()`

## Key facts

- **Config** is in `power_agent/config.py` (tracked). **Secrets** (bot token, chat ID, password, SCADA URL) are in `power_agent/secrets.json` (gitignored). Copy `secrets.example.json` to `secrets.json` and fill in your values.
- **SCADA endpoint** is a LAN-only URL (set in `secrets.json`) — the app will fail if unreachable
- **No tests** exist anywhere in the repo
- **No linter, formatter, or typechecker** is configured
- **No CI, no Makefile, no `.gitignore`**
- **Prophet** requires CmdStan (already installed in `.venv`) — first prediction call may be slow (model compilation)
- Anomaly detection needs at least 10 data points to produce results
- Default anomaly threshold is 2.5 (z-score), adjustable via `config.py` or API query param
- Dashboard auto-refreshes every 60s via `setInterval` in `static/dashboard.html`

## Telegram alerts

High-severity anomalies trigger a Telegram notification during collection.  
To enable, set these in `power_agent/config.py`:

```python
telegram_bot_token: str = "YOUR_BOT_TOKEN"
telegram_chat_id: str = "YOUR_CHAT_ID"
```

Test with: `GET /api/notify/test`

## API endpoints (all under `/api`)

`/summary`, `/trend`, `/history`, `/anomalies`, `/anomalies/check`, `/predict`, `/snapshot/latest`, `/snapshot/now`, `/notify/test`

## Common pitfalls

- `python -m power_agent` — must run from repo root, not inside `power_agent/`
- SCADA fetch will time out (10s default) if not on the correct local network — caught gracefully by collector, but `/api/snapshot/now` will return a 500 error
- Prophet predictor returns error if <10 data points exist


## Energy Interpretation Rules

The system should interpret kW data using:

### 1. Baseline comparison
Always compare current kW with:
- hourly average
- daily average
- weekly trend

### 2. Anomaly meaning
High kW ≠ always problem.
Check:
- production time
- machine load behavior
- sudden spikes vs gradual increase

### 3. Key patterns to detect
- sudden spikes (>25% jump)
- sustained high load
- night-time consumption anomalies
- rising baseline trend over days

### 4. Output priority
When generating insights:
1. anomaly detection
2. trend deviation
3. possible operational cause
4. recommended check

### 5. Communication style
- industrial language
- no chatbot behavior
- no speculation without data

## Insight Output Format

All insights must follow:

- Observation
- Deviation from baseline
- Classification (normal / anomaly)
- Possible cause (data-based only)
- Action suggestion