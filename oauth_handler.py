"""
DEPRECATED — this file has been moved to services/auth_service.py.

All imports from this module will continue to work via this shim,
but you should update your imports to:

    from services.auth_service import ...
    from services import auth_service
"""
import warnings
warnings.warn(
    "oauth_handler at the project root is deprecated. "
    "Use 'from services.auth_service import ...' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from services.auth_service import (  # noqa: F401 – re-export everything
    OAuthError,
    generate_pkce_pair,
    generate_state,
    build_authorize_url,
    exchange_code_for_token,
    refresh_access_token,
    fetch_user_profile,
    is_token_expired,
    generate_jwt,
    verify_jwt,
    get_valid_wikimedia_token,
)
