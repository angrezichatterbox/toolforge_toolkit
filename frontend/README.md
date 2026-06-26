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

The backend has **no CORS headers**, so the browser will block cross-origin calls.
Pick one of these:

### Option A — serve the frontend from the backend (recommended, zero CORS)

Add a static route to `toolforge_manager.py` (two lines):

```python
app = Flask(__name__, static_folder="frontend", static_url_path="")

@app.route("/app")
def deployr_ui():
    return app.send_static_file("index.html")
```

Then:

```bash
python toolforge_manager.py --port 5000
# open http://localhost:5000/app   (leave API base URL blank — same origin)
```

### Option B — run the frontend separately + enable CORS

```bash
pip install flask-cors
```
```python
from flask_cors import CORS
CORS(app)   # after app = Flask(__name__)
```
```bash
# terminal 1
python toolforge_manager.py --port 5000
# terminal 2
cd frontend && python -m http.server 8080
# open http://localhost:8080 → Settings → API base URL = http://localhost:5000
```

## First-time setup in the UI

1. Click **Settings**, set the **API base URL** (blank if served from the backend).
2. Enter your **Wikimedia username**, **SSH key path**, and **bastion host**, then **Save**.
3. Click **Test connection** to verify SSH reaches the bastion.
4. On a tool card, click **Deploy** — watch the live log console in the drawer.

Per-tool config edits are saved to `localStorage`; global SSH creds live on the backend.
