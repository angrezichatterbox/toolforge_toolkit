#!/usr/bin/env python3
"""
Toolforge Manager Backend App

Main entry point for the Flask-based backend server with stateless
JWT-based Wikimedia OAuth 2.0 authentication.

Authentication is handled entirely through signed JWTs stored in HTTP-only
cookies — no server-side sessions or databases are used.
"""

import time
import functools
import urllib.parse

from flask import (
    Flask,
    redirect,
    request,
    jsonify,
    render_template,
    make_response,
    g,
)

import jwt  # PyJWT — only for exception types in the decorator

import auth_config
import oauth_handler
from routes.config import config_bp
from routes.webservice import webservice_bp
from routes.deploy import deploy_bp

# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = auth_config.FLASK_SECRET_KEY

# Register Blueprints
app.register_blueprint(config_bp)
app.register_blueprint(webservice_bp)
app.register_blueprint(deploy_bp)

# ---------------------------------------------------------------------------
# Cookie Security Flag
#
# Secure cookies are only sent over HTTPS.  On plain HTTP (e.g. localhost dev)
# setting secure=True causes the browser to silently drop the cookie, which
# breaks the OAuth CSRF state check.  We therefore derive the flag from the
# actual scheme of the configured redirect URI rather than from app.debug.
# ---------------------------------------------------------------------------
USE_SECURE_COOKIES = auth_config.OAUTH_REDIRECT_URI.startswith("https://")


# ---------------------------------------------------------------------------
# JWT-Required Decorator
# ---------------------------------------------------------------------------

def jwt_required(f):
    """Decorator that protects a route with JWT authentication.

    Extracts the JWT from the ``auth_token`` cookie or the
    ``Authorization: Bearer <token>`` header, verifies it, and populates
    ``g.user_id``, ``g.username``, and ``g.jwt_payload`` for the wrapped
    view function.

    Returns 401 JSON if the token is missing, expired, or invalid.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # 1. Try the auth_token cookie first
        token = request.cookies.get("auth_token")

        # 2. Fall back to Authorization header
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]

        if not token:
            return jsonify({"authenticated": False, "error": "Missing auth token."}), 401

        # Verify the JWT
        try:
            payload = oauth_handler.verify_jwt(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"authenticated": False, "error": "Token has expired."}), 401
        except jwt.InvalidTokenError as e:
            return jsonify({"authenticated": False, "error": f"Invalid token: {e}"}), 401

        # Bind identity to request context
        g.user_id = payload["sub"]
        g.username = payload["username"]
        g.jwt_payload = payload

        return f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
# Auth Routes
# ---------------------------------------------------------------------------

@app.route("/login")
def login_page():
    """Render the visual login page.

    If the user already has a valid JWT cookie, redirect to the dashboard.
    Otherwise, render the login.html template.
    """
    token = request.cookies.get("auth_token")
    if token:
        try:
            oauth_handler.verify_jwt(token)
            return redirect("/")
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            # Stale cookie — clear it and show the login page
            response = make_response(render_template("login.html"))
            response.delete_cookie("auth_token")
            return response

    return render_template("login.html")


@app.route("/oauth/authorize")
def oauth_authorize():
    """Start the OAuth 2.0 login flow.

    Generates a PKCE pair and state, stores them in short-lived HTTP-only
    cookies (not the Flask session), and redirects the user to Wikimedia's
    authorization page.
    """
    # Generate PKCE pair and CSRF state
    code_verifier, code_challenge = oauth_handler.generate_pkce_pair()
    state = oauth_handler.generate_state()

    # Build the authorization URL
    authorize_url = oauth_handler.build_authorize_url(
        client_id=auth_config.OAUTH_CLIENT_ID,
        redirect_uri=auth_config.OAUTH_REDIRECT_URI,
        code_challenge=code_challenge,
        state=state,
    )

    # Store verifier and state in short-lived cookies (10 minutes)
    response = redirect(authorize_url)
    response.set_cookie(
        "pkce_verifier", code_verifier,
        max_age=600, httponly=True, samesite="Lax",
        secure=USE_SECURE_COOKIES,
    )
    response.set_cookie(
        "oauth_state", state,
        max_age=600, httponly=True, samesite="Lax",
        secure=USE_SECURE_COOKIES,
    )

    return response


@app.route("/callback")
def callback():
    """Handle the OAuth 2.0 callback from Wikimedia.

    Validates the state parameter, exchanges the authorization code for
    tokens, fetches the user profile, mints a JWT, and sets it in a
    secure HTTP-only cookie.
    """
    # ── Validate state (CSRF protection) ──
    received_state = request.args.get("state", "")
    expected_state = request.cookies.get("oauth_state", "")

    if not expected_state or received_state != expected_state:
        # Cookies were missing or tampered — send back to login with a clear message
        return redirect("/login?error=session_expired")

    # ── Check for errors from Wikimedia ──
    error = request.args.get("error")
    if error:
        error_desc = request.args.get("error_description", "access_denied")
        # Pass the Wikimedia error reason back to the login page
        return redirect(f"/login?error={urllib.parse.quote(error_desc)}")

    # ── Exchange authorization code for tokens ──
    code = request.args.get("code")
    if not code:
        return redirect("/login?error=no_code")

    code_verifier = request.cookies.get("pkce_verifier", "")

    try:
        token_response = oauth_handler.exchange_code_for_token(
            client_id=auth_config.OAUTH_CLIENT_ID,
            client_secret=auth_config.OAUTH_CLIENT_SECRET,
            redirect_uri=auth_config.OAUTH_REDIRECT_URI,
            code=code,
            code_verifier=code_verifier,
        )
    except oauth_handler.OAuthError:
        return redirect("/login?error=token_exchange_failed")

    # ── Fetch user profile ──
    try:
        profile = oauth_handler.fetch_user_profile(token_response["access_token"])
    except oauth_handler.OAuthError:
        return redirect("/login?error=profile_fetch_failed")

    # ── Validate that we got a usable identity ──
    user_id = str(profile.get("sub", ""))
    username = profile.get("username", "")
    if not user_id or not username:
        return redirect("/login?error=invalid_profile")

    # ── Mint JWT with user identity + Wikimedia tokens ──
    access_token = token_response["access_token"]
    refresh_token = token_response.get("refresh_token", "")
    wiki_token_expires_at = time.time() + token_response.get("expires_in", 3600)

    auth_jwt = oauth_handler.generate_jwt(
        user_id=user_id,
        username=username,
        access_token=access_token,
        refresh_token=refresh_token,
        wiki_token_expires_at=wiki_token_expires_at,
    )

    # ── Verify the JWT we just minted is valid before trusting it ──
    try:
        oauth_handler.verify_jwt(auth_jwt)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return redirect("/login?error=jwt_mint_failed")

    # ── All good — set auth_token cookie and clean up temporary cookies ──
    response = redirect("/")
    response.set_cookie(
        "auth_token", auth_jwt,
        max_age=auth_config.JWT_EXPIRATION_SECS,
        httponly=True, samesite="Lax",
        secure=USE_SECURE_COOKIES,
    )
    response.delete_cookie("pkce_verifier")
    response.delete_cookie("oauth_state")

    return response


@app.route("/logout")
def logout():
    """Clear the auth_token cookie and redirect to the login page."""
    response = redirect("/login")
    response.delete_cookie("auth_token")
    return response


@app.route("/api/me")
@jwt_required
def api_me():
    """Return the authenticated user's profile.

    This is the endpoint the frontend calls to check auth state.

    Returns:
        200: JSON with username, sub, authenticated=True
    """
    return jsonify({
        "authenticated": True,
        "username": g.username,
        "sub": g.user_id,
    })


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
            payload = oauth_handler.verify_jwt(token)
            username = payload.get("username", "Unknown")
            return render_template("index.html", username=username)
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            # Invalid or expired token — clear stale cookie and redirect to login
            response = redirect("/login")
            response.delete_cookie("auth_token")
            return response

    # No token — redirect to the login page
    return redirect("/login")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Toolforge Manager Backend App")
    parser.add_argument("--port", type=int, default=5000, help="Port to run the Flask server on")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host address to bind the Flask server to")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")

    args = parser.parse_args()

    if not auth_config.OAUTH_CLIENT_ID:
        print("\033[33m⚠ OAUTH_CLIENT_ID is not set. Set it via .env or environment variable.\033[0m")
    if not auth_config.OAUTH_CLIENT_SECRET:
        print("\033[33m⚠ OAUTH_CLIENT_SECRET is not set. Set it via .env or environment variable.\033[0m")
    if not auth_config.JWT_SECRET_KEY:
        print("\033[33m⚠ JWT_SECRET_KEY is not set. Set it via .env or environment variable.\033[0m")

    print(f"Starting Toolforge Manager Backend Server on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)
