# Deployr — Frontend

A clean, no-build dashboard for the Toolforge Manager API (`toolforge_manager.py`).
Plain HTML/CSS/JS — no framework, no bundler, no external assets.

```
frontend/
├── index.html   # markup
├── styles.css   # design system (light + dark theme)
├── app.js       # API wiring + state
└── data.js      # seed tools (placeholder repos + the real pdf-image-identifier)
```

## What it does

| UI element            | Backend endpoint              |
|-----------------------|-------------------------------|
| API status pill       | `GET /`                       |
| Settings → Save       | `POST /api/config`            |
| Settings → Test       | `POST /api/test-connection`   |
| Card **Deploy**       | `POST /api/deploy`            |
| Drawer **Refresh**    | `GET /api/webservice/status`  |
| Start / Stop / Restart| `POST /api/webservice/control`|

The backend manages **one active tool at a time** (from `~/.toolforge_config.json`).
Deployr treats each card as a deploy target: deploying or controlling a card first
sets it as the active tool (`POST /api/config { tool_name }`), then acts on it.
The `pdf-image-identifier` card (tool `picstalker`) is the real one for end-to-end testing.

## Running it

`app.py` serves this frontend from the **same origin** as the `/api/*` backend
(static files configured in `app.py`), so there are no CORS issues — one command:

```bash
pip install -r requirements.txt        # flask + PyMySQL
python app.py --port 8765
# open http://localhost:8765/          (leave API base URL blank — same origin)
```

> Avoid port `5000` (macOS AirPlay → 403) and `8080` (often Jenkins). `8765` is a safe default.
> The API discovery banner lives at `/api`; the dashboard is at `/`.

A local MariaDB/MySQL must be reachable (defaults `127.0.0.1:3306`, user `root`);
`db.py` auto-creates and seeds the `deployr` database on first start. If the DB is
down the UI still loads with the bundled fallback list.

## First-time setup in the UI

1. Click **Settings**, set the **API base URL** (blank if served from the backend).
2. Enter your **Wikimedia username**, **SSH key path**, and **bastion host**, then **Save**.
3. Click **Test connection** to verify SSH reaches the bastion.
4. On a tool card, click **Deploy** — watch the live log console in the drawer.

Per-tool config edits are saved to `localStorage`; global SSH creds live on the backend.
