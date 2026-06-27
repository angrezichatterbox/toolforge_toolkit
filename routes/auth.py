"""
Deployr — Auth Routes

Blueprint handling the full OAuth 2.0 + PKCE login flow and JWT-based
session management.

Routes
------
GET  /login              Render the login page (or redirect if already authed)
GET  /oauth/authorize    Kick off the OAuth flow — redirect to Wikimedia
GET  /callback           Handle the Wikimedia callback, mint JWT, set cookie
GET  /logout             Clear auth cookie and redirect to /login
GET  /api/me             Return the current user's identity (JWT-protected)

Decorator
---------
jwt_required  — apply to any route that requires authentication
"""

import time
import functools
import urllib.parse

import jwt  # PyJWT — for exception types only

from flask import (
    Blueprint,
    redirect,
    request,
    jsonify,
    render_template,
    make_response,
    g,
)

import configs.auth_config as auth_config
from services.auth_service import (
    generate_pkce_pair,
    generate_state,
    build_authorize_url,
    exchange_code_for_token,
    fetch_user_profile,
    generate_jwt,
    verify_jwt,
    OAuthError,
)

auth_bp = Blueprint("auth", __name__)

# ---------------------------------------------------------------------------
# Cookie Security Flag
#
# Secure cookies are only sent over HTTPS.  On plain HTTP (e.g. localhost dev)
# setting secure=True causes the browser to silently drop the cookie, which
# breaks the OAuth CSRF state check.  We derive the flag from the configured
# redirect URI rather than from app.debug.
# ---------------------------------------------------------------------------
_USE_SECURE_COOKIES = auth_config.OAUTH_REDIRECT_URI.startswith("https://")


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
        token = request.cookies.get("auth_token")

        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]

        if not token:
            return jsonify({"authenticated": False, "error": "Missing auth token."}), 401

        try:
            payload = verify_jwt(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"authenticated": False, "error": "Token has expired."}), 401
        except jwt.InvalidTokenError as e:
            return jsonify({"authenticated": False, "error": f"Invalid token: {e}"}), 401

        g.user_id     = payload["sub"]
        g.username    = payload["username"]
        g.jwt_payload = payload

        return f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
# Auth Routes
# ---------------------------------------------------------------------------

@auth_bp.route("/login")
def login_page():
    """Render the visual login page.

    If the user already has a valid JWT cookie, redirect to the dashboard.
    Otherwise, render the login.html template.
    """
    token = request.cookies.get("auth_token")
    if token:
        try:
            verify_jwt(token)
            return redirect("/")
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            # Stale cookie — clear it and show the login page
            response = make_response(render_template("login.html"))
            response.delete_cookie("auth_token")
            return response

    return render_template("login.html")


@auth_bp.route("/oauth/authorize")
def oauth_authorize():
    """Start the OAuth 2.0 login flow.

    Generates a PKCE pair and state, stores them in short-lived HTTP-only
    cookies, and redirects the user to Wikimedia's authorization page.
    """
    code_verifier, code_challenge = generate_pkce_pair()
    state = generate_state()

    authorize_url = build_authorize_url(
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
        secure=_USE_SECURE_COOKIES,
    )
    response.set_cookie(
        "oauth_state", state,
        max_age=600, httponly=True, samesite="Lax",
        secure=_USE_SECURE_COOKIES,
    )
    return response


@auth_bp.route("/callback")
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
        return redirect("/login?error=session_expired")

    # ── Check for errors from Wikimedia ──
    error = request.args.get("error")
    if error:
        error_desc = request.args.get("error_description", "access_denied")
        return redirect(f"/login?error={urllib.parse.quote(error_desc)}")

    # ── Exchange authorization code for tokens ──
    code = request.args.get("code")
    if not code:
        return redirect("/login?error=no_code")

    code_verifier = request.cookies.get("pkce_verifier", "")

    try:
        token_response = exchange_code_for_token(
            client_id=auth_config.OAUTH_CLIENT_ID,
            client_secret=auth_config.OAUTH_CLIENT_SECRET,
            redirect_uri=auth_config.OAUTH_REDIRECT_URI,
            code=code,
            code_verifier=code_verifier,
        )
    except OAuthError:
        return redirect("/login?error=token_exchange_failed")

    # ── Fetch user profile ──
    try:
        profile = fetch_user_profile(token_response["access_token"])
    except OAuthError:
        return redirect("/login?error=profile_fetch_failed")

    # ── Validate that we got a usable identity ──
    user_id  = str(profile.get("sub", ""))
    username = profile.get("username", "")
    if not user_id or not username:
        return redirect("/login?error=invalid_profile")

    # ── Mint JWT with user identity + Wikimedia tokens ──
    access_token          = token_response["access_token"]
    refresh_token         = token_response.get("refresh_token", "")
    wiki_token_expires_at = time.time() + token_response.get("expires_in", 3600)

    auth_jwt = generate_jwt(
        user_id=user_id,
        username=username,
        access_token=access_token,
        refresh_token=refresh_token,
        wiki_token_expires_at=wiki_token_expires_at,
    )

    # ── Verify the JWT we just minted is valid before trusting it ──
    try:
        verify_jwt(auth_jwt)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return redirect("/login?error=jwt_mint_failed")

    # ── All good — set auth_token cookie and clean up temporary cookies ──
    response = redirect("/")
    response.set_cookie(
        "auth_token", auth_jwt,
        max_age=auth_config.JWT_EXPIRATION_SECS,
        httponly=True, samesite="Lax",
        secure=_USE_SECURE_COOKIES,
    )
    response.delete_cookie("pkce_verifier")
    response.delete_cookie("oauth_state")
    return response


@auth_bp.route("/logout")
def logout():
    """Clear the auth_token cookie and redirect to the login page."""
    response = redirect("/login")
    response.delete_cookie("auth_token")
    return response


@auth_bp.route("/api/me")
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
