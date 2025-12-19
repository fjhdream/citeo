"""Authentication package for Citeo API.

Provides API Key and JWT authentication via FastAPI dependencies.
"""

from citeo.auth.combined import CombinedAuthenticator
from citeo.auth.dependencies import get_current_user, require_auth
from citeo.auth.jwt_auth import (
    JWTAuthenticator,
    create_access_token,
    create_refresh_token,
)
from citeo.auth.models import AuthUser, TokenPayload, TokenResponse
from citeo.auth.token_storage import get_token_storage

__all__ = [
    "AuthUser",
    "CombinedAuthenticator",
    "JWTAuthenticator",
    "TokenPayload",
    "TokenResponse",
    "create_access_token",
    "create_refresh_token",
    "get_current_user",
    "get_token_storage",
    "require_auth",
]
