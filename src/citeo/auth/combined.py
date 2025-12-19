"""Combined authenticator supporting multiple auth methods.

Reason: Allow clients to authenticate via either API Key OR JWT,
providing flexibility for different use cases.
"""

import structlog

from citeo.auth.api_key import APIKeyAuthenticator
from citeo.auth.exceptions import TokenExpiredError
from citeo.auth.jwt_auth import JWTAuthenticator
from citeo.auth.models import AuthUser

logger = structlog.get_logger()


class CombinedAuthenticator:
    """Authenticator that accepts either API Key or JWT.

    Reason: Single-user mode means both methods authenticate the same user.
    JWT is checked first (more common for programmatic access), then API Key.
    """

    def __init__(
        self,
        api_key: str | None = None,
        jwt_secret: str | None = None,
    ):
        """Initialize with authentication credentials.

        Args:
            api_key: API key for X-API-Key header auth.
            jwt_secret: Secret key for JWT token auth.

        At least one must be provided for authentication to work.
        """
        self._api_key_auth = APIKeyAuthenticator(api_key) if api_key else None
        self._jwt_auth = JWTAuthenticator(jwt_secret) if jwt_secret else None

    async def authenticate(
        self,
        api_key: str | None = None,
        bearer_token: str | None = None,
    ) -> AuthUser | None:
        """Authenticate using any available method.

        Priority order:
        1. JWT token (if provided and JWT auth configured)
        2. API Key (if provided and API Key auth configured)

        Args:
            api_key: API key from header or query parameter.
            bearer_token: JWT token from Authorization header.

        Returns:
            AuthUser if any method succeeds, None otherwise.

        Raises:
            TokenExpiredError: If JWT token is expired (allows specific handling).
        """
        # Try JWT first (preferred for programmatic access)
        if bearer_token and self._jwt_auth:
            try:
                result = await self._jwt_auth.authenticate(bearer_token=bearer_token)
                if result:
                    return result
            except TokenExpiredError:
                # Re-raise for specific handling in dependencies
                raise

        # Fall back to API Key
        if api_key and self._api_key_auth:
            result = await self._api_key_auth.authenticate(api_key=api_key)
            if result:
                return result

        return None

    def validate_credentials(self) -> bool:
        """Check if at least one auth method is configured."""
        api_key_valid = self._api_key_auth and self._api_key_auth.validate_credentials()
        jwt_valid = self._jwt_auth and self._jwt_auth.validate_credentials()
        return api_key_valid or jwt_valid
