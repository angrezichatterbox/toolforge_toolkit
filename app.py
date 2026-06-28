#!/usr/bin/env python3
"""
Toolforge Manager Backend App
Main entry point for the Flask-based backend server.
"""

import os

from dotenv import load_dotenv
from flask import Flask, jsonify

# Load environment variables from .env (SSH key path, bastion host, DB creds).
load_dotenv()

from extensions import db, migrate
from routes.config import config_bp
from routes.webservice import webservice_bp
from routes.deploy import deploy_bp
from routes.tools import tools_bp

# ── Database configuration ─────────────────────────────────────────────
_DB_USER = os.environ.get("DEPLOYR_DB_USER", "")
_DB_PASS = os.environ.get("DEPLOYR_DB_PASS", "")
_DB_HOST = os.environ.get("DEPLOYR_DB_HOST", "127.0.0.1")
_DB_PORT = os.environ.get("DEPLOYR_DB_PORT", "3306")
_DB_NAME = os.environ.get("DEPLOYR_DB_NAME", "deployr")

FRONTEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
app = Flask(__name__, static_folder=FRONTEND, static_url_path="")

# Flask-SQLAlchemy — MySQL via PyMySQL driver
app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://{_DB_USER}:{_DB_PASS}@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}"
    "?charset=utf8mb4"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Bind extensions to the app
db.init_app(app)
migrate.init_app(app, db)

# Import models so Alembic/Flask-Migrate can detect them for autogenerate.
import models  # noqa: F401  (side-effect import — registers metadata)

# Register Blueprints
app.register_blueprint(config_bp)
app.register_blueprint(webservice_bp)
app.register_blueprint(deploy_bp)
app.register_blueprint(tools_bp)


# ── CLI command: flask init-db ─────────────────────────────────────────
@app.cli.command("init-db")
def init_db_command():
    """Seed the database with default data (run after `flask db upgrade`)."""
    import db as _db
    import routes.tools as _tools_mod
    try:
        _db.init_db()
        _tools_mod.DB_OK = True
        print(f"[deployr] DB ready: {_db.DB_CONF['host']}:{_db.DB_CONF['port']}/{_db.DB_NAME}")
    except Exception as e:
        print(f"[deployr] init-db failed: {e}")


@app.route("/")
def index():
    """Serves the Deployr dashboard."""
    return app.send_static_file("index.html")

@app.route("/api")
def api_info():
    """API discovery banner."""
    return jsonify({
        "status": "ok",
        "message": "Toolforge Manager API is running",
        "endpoints": [
            {"path": "/api/tools", "methods": ["GET", "POST"]},
            {"path": "/api/tools/inspect", "methods": ["POST"]},
            {"path": "/api/tools/<id>", "methods": ["DELETE"]},
            {"path": "/api/config", "methods": ["GET", "POST"]},
            {"path": "/api/test-connection", "methods": ["POST"]},
            {"path": "/api/deploy", "methods": ["POST"]},
            {"path": "/api/webservice/status", "methods": ["POST"]},
            {"path": "/api/webservice/control", "methods": ["POST"]}
        ]
    })

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Toolforge Manager Backend App")
    parser.add_argument("--port", type=int, default=5000, help="Port to run the Flask server on")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host address to bind the Flask server to")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")

    args = parser.parse_args()

    with app.app_context():
        import db as _db
        import routes.tools as _tools_mod
        try:
            _db.init_db()
            _tools_mod.DB_OK = True
            print(f"[deployr] DB connected: {_db.DB_CONF['host']}:{_db.DB_CONF['port']}/{_db.DB_NAME}")
        except Exception as _db_err:
            _tools_mod.DB_OK = False
            print(f"[deployr] DB unavailable ({_db_err}); /api/tools will return empty.")

    print(f"Starting Toolforge Manager Backend Server on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)
