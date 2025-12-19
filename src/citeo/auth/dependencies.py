"""FastAPI dependency injection for authentication.

Reason: Centralized auth logic via dependencies allows clean
separation of concerns and easy testing.
"""

import structlog
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, APIKeyQuery, HTTPAuthorizationCredentials, HTTPBearer

from citeo.auth.combined import CombinedAuthenticator
from citeo.auth.exceptions import TokenExpiredError
from citeo.auth.models import AuthUser
from citeo.config.settings import settings

logger = structlog.get_logger()

# Security schemes for OpenAPI documentation
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)

# Global authenticator instance (initialized lazily)
_authenticator: CombinedAuthenticator | None = None


def get_authenticator() -> CombinedAuthenticator:
    """Get or create the global authenticator instance.

    Reason: Lazy initialization allows settings to be loaded before
    authenticator is created.
    """
    global _authenticator
    if _authenticator is None:
        _authenticator = CombinedAuthenticator(
            api_key=settings.auth_api_key.get_secret_value() if settings.auth_api_key else None,
            jwt_secret=(
                settings.auth_jwt_secret.get_secret_value() if settings.auth_jwt_secret else None
            ),
        )

        if not _authenticator.validate_credentials():
            logger.warning(
                "No authentication credentials configured. "
                "Set AUTH_API_KEY or AUTH_JWT_SECRET in environment."
            )

    return _authenticator


async def get_current_user(
    request: Request,
    api_key_header_value: str | None = Security(api_key_header),
    api_key_query_value: str | None = Security(api_key_query),
    bearer_credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> AuthUser | None:
    """Extract and validate authentication credentials.

    This dependency does NOT raise exceptions - it returns None if not authenticated.
    Use require_auth() for protected endpoints.

    Args:
        request: FastAPI request object.
        api_key_header_value: API key from X-API-Key header.
        api_key_query_value: API key from query parameter.
        bearer_credentials: Bearer token from Authorization header.

    Returns:
        AuthUser if authenticated, None otherwise.
    """
    # Skip if auth is disabled
    if not settings.auth_enabled:
        return AuthUser(user_id="default", auth_method="disabled")

    # Get API key from header or query (header takes precedence)
    api_key = api_key_header_value or api_key_query_value

    # Get bearer token
    bearer_token = bearer_credentials.credentials if bearer_credentials else None

    # Skip auth if neither provided
    if not api_key and not bearer_token:
        return None

    authenticator = get_authenticator()

    try:
        user = await authenticator.authenticate(api_key=api_key, bearer_token=bearer_token)
        if user:
            # Store in request state for access in route handlers
            request.state.auth_user = user
        return user
    except TokenExpiredError:
        # Will be handled by require_auth
        return None


async def require_auth(
    user: AuthUser | None = Depends(get_current_user),
) -> AuthUser:
    """Dependency that requires authentication.

    Use this for protected endpoints. Raises 401 if not authenticated.

    Args:
        user: Result from get_current_user dependency.

    Returns:
        Authenticated AuthUser.

    Raises:
        HTTPException: 401 if not authenticated.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Provide X-API-Key header or Bearer token.",
            headers={"WWW-Authenticate": "Bearer, ApiKey"},
        )
    return user


def reset_authenticator() -> None:
    """Reset global authenticator (for testing).

    Reason: Allows tests to reinitialize with different settings.
    """
    global _authenticator
    _authenticator = None
