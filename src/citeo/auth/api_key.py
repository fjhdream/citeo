"""API Key authenticator implementation."""

import secrets

import structlog

from citeo.auth.models import AuthUser

logger = structlog.get_logger()


class APIKeyAuthenticator:
    """API Key authentication implementation.

    Reason: Simple single-key validation for single-user mode.
    Uses secrets.compare_digest for timing-attack resistant comparison.
    """

    def __init__(self, api_key: str):
        """Initialize with the expected API key.

        Args:
            api_key: The valid API key to check against.
        """
        self._api_key = api_key

    async def authenticate(
        self,
        api_key: str | None = None,
        bearer_token: str | None = None,
    ) -> AuthUser | None:
        """Authenticate using API key.

        Args:
            api_key: API key from header or query parameter.
            bearer_token: Ignored by this authenticator.

        Returns:
            AuthUser if API key matches, None otherwise.
        """
        if not api_key:
            return None

        # Reason: Use constant-time comparison to prevent timing attacks
        if secrets.compare_digest(api_key, self._api_key):
            logger.debug("API key authentication successful")
            return AuthUser(auth_method="api_key")

        logger.warning("API key authentication failed", provided_key_length=len(api_key))
        return None

    def validate_credentials(self) -> bool:
        """Check if API key is configured."""
        return bool(self._api_key and len(self._api_key) >= 16)
