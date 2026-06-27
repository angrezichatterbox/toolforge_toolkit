#!/usr/bin/env python3
"""
Deployr — Toolforge Manager Backend App

Main entry point for the Flask-based backend server with stateless
JWT-based Wikimedia OAuth 2.0 authentication.

Authentication is handled entirely through signed JWTs stored in HTTP-only
cookies — no server-side sessions or databases are used.

Routes are organized as Blueprints under routes/:
  routes/auth.py        — OAuth 2.0 login flow + jwt_required decorator
  routes/config.py      — Toolforge SSH / config API
  routes/webservice.py  — Toolforge webservice lifecycle API
  routes/deploy.py      — Toolforge deployment pipeline API

Business logic lives under services/:
  services/auth_service.py   — PKCE, token exchange, JWT mint/verify
  services/config_service.py — Config persistence
  services/ssh_service.py    — SSH command execution
  services/deploy_service.py — Deployment pipeline
"""

import jwt  # PyJWT — used only for exception type check in the home route

from flask import Flask, redirect, request, render_template

import configs.auth_config as auth_config
from services.auth_service import verify_jwt

from routes.auth import auth_bp
from routes.config import config_bp
from routes.webservice import webservice_bp
from routes.deploy import deploy_bp

# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = auth_config.FLASK_SECRET_KEY

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(config_bp)
app.register_blueprint(webservice_bp)
app.register_blueprint(deploy_bp)


# ---------------------------------------------------------------------------
# Home Route
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Home page — dashboard for authenticated users.

    Unauthenticated visitors are redirected to /login.
    """
    token = request.cookies.get("auth_token")
    if token:
        try:
            payload  = verify_jwt(token)
            username = payload.get("username", "Unknown")
            return render_template("index.html", username=username)
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            # Invalid or expired token — clear stale cookie and redirect
            response = redirect("/login")
            response.delete_cookie("auth_token")
            return response

    return redirect("/login")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Deployr — Toolforge Manager Backend")
    parser.add_argument("--port",  type=int, default=5000,       help="Port to listen on")
    parser.add_argument("--host",  type=str, default="127.0.0.1", help="Host address to bind")
    parser.add_argument("--debug", action="store_true",           help="Enable Flask debug mode")
    args = parser.parse_args()

    if not auth_config.OAUTH_CLIENT_ID:
        print("\033[33m⚠ OAUTH_CLIENT_ID is not set.\033[0m")
    if not auth_config.OAUTH_CLIENT_SECRET:
        print("\033[33m⚠ OAUTH_CLIENT_SECRET is not set.\033[0m")
    if not auth_config.JWT_SECRET_KEY:
        print("\033[33m⚠ JWT_SECRET_KEY is not set.\033[0m")

    print(f"Starting Deployr on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)
