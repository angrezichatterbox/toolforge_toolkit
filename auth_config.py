"""
Deployr — Central Configuration

OAuth 2.0 endpoints, client credentials, and JWT settings for
Wikimedia authentication.
Set credentials via environment variables or a local .env file.
"""

import os

# Load .env file manually if it exists to populate os.environ
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _val = _line.split("=", 1)
                os.environ.setdefault(_key.strip(), _val.strip().strip("'\""))

# ---------------------------------------------------------------------------
# Wikimedia OAuth 2.0 Endpoints
# ---------------------------------------------------------------------------
OAUTH_AUTHORIZE_URL = "https://meta.wikimedia.org/w/rest.php/oauth2/authorize"
OAUTH_TOKEN_URL = "https://meta.wikimedia.org/w/rest.php/oauth2/access_token"
OAUTH_PROFILE_URL = "https://meta.wikimedia.org/w/rest.php/oauth2/resource/profile"

# ---------------------------------------------------------------------------
# OAuth Client Credentials
# Register at: https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration/propose/oauth2
# ---------------------------------------------------------------------------
OAUTH_CLIENT_ID = os.environ["OAUTH_CLIENT_ID"]
OAUTH_CLIENT_SECRET = os.environ["OAUTH_CLIENT_SECRET"]

# ---------------------------------------------------------------------------
# Flask Configuration
# ---------------------------------------------------------------------------
FLASK_SECRET_KEY = os.environ["FLASK_SECRET_KEY"]
OAUTH_REDIRECT_URI = os.environ.get("OAUTH_REDIRECT_URI", "http://localhost:5000/callback")

# ---------------------------------------------------------------------------
# JWT Configuration
# ---------------------------------------------------------------------------
JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]
JWT_EXPIRATION_SECS = 3600  # 1 hour
