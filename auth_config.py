"""
DEPRECATED — this file has been moved to configs/auth_config.py.

All imports from this module will continue to work via this shim,
but you should update your imports to:

    from configs.auth_config import ...
    import configs.auth_config as auth_config
"""
import warnings
warnings.warn(
    "auth_config at the project root is deprecated. "
    "Use 'from configs.auth_config import ...' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from configs.auth_config import (  # noqa: F401 – re-export everything
    OAUTH_AUTHORIZE_URL,
    OAUTH_TOKEN_URL,
    OAUTH_PROFILE_URL,
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    FLASK_SECRET_KEY,
    OAUTH_REDIRECT_URI,
    JWT_SECRET_KEY,
    JWT_EXPIRATION_SECS,
)
