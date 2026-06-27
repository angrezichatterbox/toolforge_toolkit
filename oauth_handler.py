"""
Deployr — OAuth 2.0 + JWT Handler for Wikimedia

A framework-agnostic module implementing the OAuth 2.0 Authorization Code
flow with PKCE against meta.wikimedia.org, plus stateless JWT token
management.

This module never imports Flask or any web framework — the web app calls
*into* this module.

Public API
----------
generate_pkce_pair()                → (verifier, challenge)
build_authorize_url(...)            → str
exchange_code_for_token(...)        → dict
refresh_access_token(...)           → dict
fetch_user_profile(token)           → dict
is_token_expired(expires_at)        → bool
generate_jwt(...)                   → str
verify_jwt(token)                   → dict
get_valid_wikimedia_token(payload)  → (access_token, refresh_token, expires_at, refreshed)
"""

import hashlib
import secrets
import base64
import json
import time
import urllib.request
import urllib.parse
import urllib.error

import jwt  # PyJWT

from auth_config import (
    OAUTH_AUTHORIZE_URL,
    OAUTH_TOKEN_URL,
    OAUTH_PROFILE_URL,
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    JWT_SECRET_KEY,
    JWT_EXPIRATION_SECS,
)


# ---------------------------------------------------------------------------
# PKCE (Proof Key for Code Exchange)
# ---------------------------------------------------------------------------

def generate_pkce_pair():
    """Generate a PKCE code_verifier and code_challenge (S256).

    Returns:
        tuple: (code_verifier, code_challenge) — both are URL-safe strings.
               code_verifier is 128 characters of random URL-safe base64.
               code_challenge is the SHA-256 hash of the verifier, base64url-encoded.
    """
    # Generate a high-entropy random verifier (96 random bytes → 128 base64url chars)
    verifier_bytes = secrets.token_bytes(96)
    code_verifier = base64.urlsafe_b64encode(verifier_bytes).rstrip(b"=").decode("ascii")

    # SHA-256 hash → base64url encode (no padding) = code_challenge
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    return code_verifier, code_challenge


def generate_state():
    """Generate a random state parameter for CSRF protection.

    Returns:
        str: A 32-character hex string.
    """
    return secrets.token_hex(16)


# ---------------------------------------------------------------------------
# Authorization URL
# ---------------------------------------------------------------------------

def build_authorize_url(client_id, redirect_uri, code_challenge, state):
    """Build the Wikimedia OAuth 2.0 authorization URL.

    The web app should redirect the user's browser to this URL.

    Args:
        client_id:      The OAuth consumer client ID.
        redirect_uri:   The callback URL (must match registration).
        code_challenge:  The PKCE code_challenge (S256).
        state:          A random string for CSRF protection.

    Returns:
        str: The full authorization URL with query parameters.
    """
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return f"{OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


# ---------------------------------------------------------------------------
# Token Exchange
# ---------------------------------------------------------------------------

def exchange_code_for_token(client_id, client_secret, redirect_uri, code, code_verifier):
    """Exchange an authorization code for an access token.

    Args:
        client_id:      The OAuth consumer client ID.
        client_secret:  The OAuth consumer client secret.
        redirect_uri:   The callback URL (must match the authorize request).
        code:           The authorization code received in the callback.
        code_verifier:  The original PKCE code_verifier.

    Returns:
        dict: Token response with keys: access_token, token_type, expires_in,
              refresh_token.

    Raises:
        OAuthError: If the token exchange fails.
    """
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }

    return _post_token_request(data)


def refresh_access_token(client_id, client_secret, refresh_token):
    """Refresh an expired access token using a refresh token.

    Args:
        client_id:      The OAuth consumer client ID.
        client_secret:  The OAuth consumer client secret.
        refresh_token:  The refresh token from the original exchange.

    Returns:
        dict: New token response with keys: access_token, token_type,
              expires_in, refresh_token.

    Raises:
        OAuthError: If the refresh fails (user may need to re-login).
    """
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    return _post_token_request(data)


# ---------------------------------------------------------------------------
# User Profile
# ---------------------------------------------------------------------------

def fetch_user_profile(access_token):
    """Fetch the authenticated user's profile from Wikimedia.

    Uses the OAuth 2.0 resource/profile endpoint (OIDC UserInfo).

    Args:
        access_token: A valid Bearer access token.

    Returns:
        dict: User profile with keys: sub, username, editcount,
              confirmed_email, blocked, registered, groups, rights,
              and optionally realname, email.

    Raises:
        OAuthError: If the profile request fails.
    """
    req = urllib.request.Request(
        OAUTH_PROFILE_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "Deployr/1.0 (Toolforge Deployment Suite)",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise OAuthError(
            f"Profile request failed (HTTP {e.code}): {body}"
        ) from e
    except urllib.error.URLError as e:
        raise OAuthError(f"Profile request failed: {e.reason}") from e


# ---------------------------------------------------------------------------
# Token Expiry Check
# ---------------------------------------------------------------------------

def is_token_expired(expires_at):
    """Check whether an access token has expired.

    Uses a 60-second safety margin so we refresh *before* the token
    actually expires — avoids race conditions with in-flight requests.

    Args:
        expires_at: Unix timestamp (float) when the token expires.

    Returns:
        bool: True if the token is expired or will expire within 60 seconds.
    """
    return time.time() >= (expires_at - 60)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class OAuthError(Exception):
    """Raised when an OAuth operation fails."""
    pass


def _post_token_request(data):
    """Send a POST request to the Wikimedia token endpoint.

    Args:
        data: dict of form-encoded POST parameters.

    Returns:
        dict: Parsed JSON response.

    Raises:
        OAuthError: On HTTP or network errors.
    """
    encoded_data = urllib.parse.urlencode(data).encode("utf-8")

    req = urllib.request.Request(
        OAUTH_TOKEN_URL,
        data=encoded_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Deployr/1.0 (Toolforge Deployment Suite)",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise OAuthError(
            f"Token request failed (HTTP {e.code}): {body}"
        ) from e
    except urllib.error.URLError as e:
        raise OAuthError(f"Token request failed: {e.reason}") from e


# ---------------------------------------------------------------------------
# JWT Management
# ---------------------------------------------------------------------------

def generate_jwt(user_id, username, access_token, refresh_token, wiki_token_expires_at):
    """Mint a signed JWT containing user identity and Wikimedia tokens.

    The JWT is signed with HS256 using JWT_SECRET_KEY.  It embeds
    the Wikimedia OAuth tokens so no server-side storage is required.

    Args:
        user_id:                Wikimedia 'sub' claim (unique user identifier).
        username:               Wikimedia username.
        access_token:           Wikimedia OAuth access token.
        refresh_token:          Wikimedia OAuth refresh token.
        wiki_token_expires_at:  Unix timestamp when the Wikimedia access
                                token expires.

    Returns:
        str: Encoded JWT string.
    """
    now = time.time()
    payload = {
        "sub": str(user_id),
        "username": username,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "wiki_token_expires_at": wiki_token_expires_at,
        "iat": now,
        "exp": now + JWT_EXPIRATION_SECS,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")


def verify_jwt(token):
    """Decode and validate a JWT.

    Verifies the HS256 signature and checks that the token has not expired.

    Args:
        token: The encoded JWT string.

    Returns:
        dict: The decoded payload containing all claims.

    Raises:
        jwt.ExpiredSignatureError:  If the token has expired.
        jwt.InvalidTokenError:      If the signature is invalid or the
                                    token is malformed.
    """
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])


def get_valid_wikimedia_token(jwt_payload):
    """Return a valid Wikimedia access token, refreshing if necessary.

    Inspects the decoded JWT payload to determine whether the embedded
    Wikimedia access token is still valid.  If it has expired, the refresh
    flow is executed automatically.

    Args:
        jwt_payload: Decoded JWT payload dict (from verify_jwt).

    Returns:
        tuple: (access_token, refresh_token, expires_at, refreshed)
            - access_token:  A valid Wikimedia access token.
            - refresh_token: The current (possibly rotated) refresh token.
            - expires_at:    Unix timestamp of the new expiry.
            - refreshed:     True if the token was refreshed, False if the
                             existing token was still valid.  When True the
                             caller should mint a new JWT with the updated
                             tokens.

    Raises:
        OAuthError: If the refresh request fails.
    """
    access_token = jwt_payload["access_token"]
    current_refresh = jwt_payload["refresh_token"]
    expires_at = jwt_payload["wiki_token_expires_at"]

    if not is_token_expired(expires_at):
        return access_token, current_refresh, expires_at, False

    # Token expired — refresh it
    token_response = refresh_access_token(
        client_id=OAUTH_CLIENT_ID,
        client_secret=OAUTH_CLIENT_SECRET,
        refresh_token=current_refresh,
    )

    new_access_token = token_response["access_token"]
    new_refresh_token = token_response.get("refresh_token", current_refresh)
    new_expires_at = time.time() + token_response.get("expires_in", 3600)

    return new_access_token, new_refresh_token, new_expires_at, True
