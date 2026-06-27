#!/usr/bin/env python3
"""
Toolforge Manager Backend App
Main entry point for the Flask-based backend server.
"""

import os

from flask import Flask, jsonify
from routes.config import config_bp
from routes.webservice import webservice_bp
from routes.deploy import deploy_bp
from routes.tools import tools_bp

# Serve the Deployr frontend from the same origin as the API (no CORS, single
# entry point). Static files (styles.css, app.js, data.js) resolve from "/".
FRONTEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
app = Flask(__name__, static_folder=FRONTEND, static_url_path="")

# Register Blueprints
app.register_blueprint(config_bp)
app.register_blueprint(webservice_bp)
app.register_blueprint(deploy_bp)
app.register_blueprint(tools_bp)

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
            {"path": "/api/webservice/status", "methods": ["GET"]},
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
    
    print(f"Starting Toolforge Manager Backend Server on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)
