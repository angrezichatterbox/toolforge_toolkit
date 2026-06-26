#!/usr/bin/env python3
"""
Dev runner for Deployr: serves the frontend/ UI from the same origin as the
Toolforge Manager API (so there are no CORS issues), without modifying
toolforge_manager.py. Run:  python3 run_deployr.py --port 8080
Then open:  http://localhost:8080/
"""
import argparse
import os
from toolforge_manager import app  # reuses all /api/* routes

FRONTEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")


@app.route("/ui")
@app.route("/ui/")
def deployr_ui():
    return app.send_static_file("index.html")


# Serve frontend assets (index.html, styles.css, app.js, data.js) from /
@app.route("/<path:filename>")
def deployr_assets(filename):
    full = os.path.join(FRONTEND, filename)
    if os.path.isfile(full):
        return app.send_static_file(filename)
    return ("Not found", 404)


# Make "/" serve the dashboard instead of the API JSON banner in dev.
app.view_functions["index"] = deployr_ui

if __name__ == "__main__":
    app.static_folder = FRONTEND
    app.static_url_path = ""
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()
    # rebind static config before serving
    app.static_folder = FRONTEND
    print(f"Deployr UI → http://{args.host}:{args.port}/")
    app.run(host=args.host, port=args.port, debug=False)
