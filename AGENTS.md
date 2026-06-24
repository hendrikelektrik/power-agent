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
- **No CI, no Makefile**
- **Prophet** requires CmdStan (already installed in `.venv`) — first prediction call may be slow (model compilation)
- Anomaly detection needs at least 10 data points to produce results
- Default anomaly threshold is 2.5 (z-score), adjustable via `config.py` or API query param
- Dashboard auto-refreshes every 60s via `setInterval` in `static/dashboard.html`

## Telegram alerts

The system sends notifications via Telegram for:
- **Anomalies** (z>3) — immediate on detection during collection
- **SCADA offline** — when fetch fails (rate-limited 1/hour)
- **SCADA restored** — when fetch recovers
- **Daily summary** — scheduled time (default 07:00, configurable via admin)
- **Manual test** — via `/api/notify/test` or admin page

All events can be toggled on/off from the admin page. Notification history is persisted in the `notifications` table in `history.db`.

## Bot commands

The bot polls Telegram via long-poll (30s timeout, 2s interval) and responds to:
- `/start` — list commands
- `/status` — live readings
- `/anomalies` — latest anomalies
- `/predict` — 24h forecast
- `/summary` — trigger daily summary

Bot username: **@dmcpower_bot**

## Admin page

- Password-protected (`admin_password` in `secrets.json`)
- Login/Logout button at sidebar bottom
- Admin link hidden until authenticated
- Test notification button
- Daily summary time setting (persisted in DB)
- Notification event toggles (enable/disable each type)

## Secrets

All secrets in `power_agent/secrets.json` (gitignored):
- `telegram_bot_token`
- `telegram_chat_id`
- `admin_password`
- Per-plant `scada_url` overrides

## API endpoints (all under `/api`)

`/summary`, `/trend`, `/history`, `/anomalies`, `/anomalies/check`, `/predict`, `/snapshot/latest`, `/snapshot/now`, `/notify/status`, `/notify/history`, `/notify/summary`, `/notify/test`, `/bot/info`, `/bot/test`, `/admin/status`, `/admin/login`, `/admin/settings`

## Static pages

- `/static/dashboard.html` — live monitoring
- `/static/anomalies.html` — real-time anomaly report
- `/static/predict.html` — forecast with chart
- `/static/notifications.html` — notification history log
- `/static/bot.html` — Telegram bot info and commands
- `/static/admin.html` — admin settings (password-protected)

## Common pitfalls

- `python -m power_agent` — must run from repo root, not inside `power_agent/`
- SCADA fetch will time out (10s default) if not on the correct local network — caught gracefully by collector, but `/api/snapshot/now` will return a 500 error
- Prophet predictor returns error if <10 data points exist
- Only one instance of the app should run at a time (Telegram polling conflicts with 409)
- `data/` directory is auto-created; no manual setup needed


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

## Recent updates (2026-06-23)

- Notifications page: history log + Telegram channel subscribe card
- Admin page: password login, test button, summary time, notification toggles
- Login in sidebar: Login/Logout at bottom; Admin link hidden until auth
- Notification persistence: stored in SQLite, survives restart
- SCADA offline/online alerts with rate limiting
- Daily summary: automated at configurable time, manual trigger
- Notification toggles: enable/disable each event type
- Secrets separation: `secrets.json` (gitignored) + `secrets.example.json`
- Telegram bot polling: `/start`, `/status`, `/anomalies`, `/predict`, `/summary`
- Telegram Bot page: bot status, commands list, link
- Bug fix: auto-create `data/` directory for SQLite
