"""Token storage for managing refresh tokens.

Reason: Stores refresh tokens to enable revocation and tracking.
Simple in-memory implementation suitable for single-instance deployment.
For production with multiple instances, use Redis or database.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import structlog

logger = structlog.get_logger()


@dataclass
class RefreshTokenRecord:
    """Refresh token record.

    Attributes:
        token_id: Unique token identifier (jti claim).
        user_id: User identifier.
        created_at: Token creation timestamp.
        expires_at: Token expiration timestamp.
        revoked: Whether token has been revoked.
    """

    token_id: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    revoked: bool = False


class TokenStorage(Protocol):
    """Token storage interface.

    Reason: Using Protocol for flexibility to swap implementations
    (in-memory, Redis, database) without changing code.
    """

    async def store_refresh_token(
        self,
        token_id: str,
        user_id: str,
        expires_at: datetime,
    ) -> None:
        """Store a refresh token record.

        Args:
            token_id: Unique token identifier.
            user_id: User identifier.
            expires_at: Token expiration timestamp.
        """
        ...

    async def is_token_valid(self, token_id: str) -> bool:
        """Check if a refresh token is valid (exists and not revoked).

        Args:
            token_id: Token identifier to check.

        Returns:
            True if token is valid, False otherwise.
        """
        ...

    async def revoke_token(self, token_id: str) -> bool:
        """Revoke a refresh token.

        Args:
            token_id: Token identifier to revoke.

        Returns:
            True if token was revoked, False if not found.
        """
        ...

    async def revoke_user_tokens(self, user_id: str) -> int:
        """Revoke all refresh tokens for a user.

        Args:
            user_id: User identifier.

        Returns:
            Number of tokens revoked.
        """
        ...

    async def cleanup_expired(self) -> int:
        """Remove expired tokens from storage.

        Returns:
            Number of tokens removed.
        """
        ...


class InMemoryTokenStorage:
    """In-memory token storage implementation.

    Reason: Simple implementation suitable for single-instance deployment.
    All tokens are lost on restart, which is acceptable for refresh tokens.
    """

    def __init__(self) -> None:
        """Initialize empty token storage."""
        # Dict of token_id -> RefreshTokenRecord
        self._tokens: dict[str, RefreshTokenRecord] = {}

    async def store_refresh_token(
        self,
        token_id: str,
        user_id: str,
        expires_at: datetime,
    ) -> None:
        """Store a refresh token record."""
        record = RefreshTokenRecord(
            token_id=token_id,
            user_id=user_id,
            created_at=datetime.utcnow(),
            expires_at=expires_at,
            revoked=False,
        )
        self._tokens[token_id] = record
        logger.debug(
            "Refresh token stored",
            token_id=token_id,
            user_id=user_id,
            expires_at=expires_at.isoformat(),
        )

    async def is_token_valid(self, token_id: str) -> bool:
        """Check if a refresh token is valid."""
        record = self._tokens.get(token_id)
        if not record:
            logger.debug("Token not found", token_id=token_id)
            return False

        # Check if revoked
        if record.revoked:
            logger.warning("Token is revoked", token_id=token_id)
            return False

        # Check if expired
        now = datetime.utcnow()
        if now > record.expires_at:
            logger.debug("Token expired", token_id=token_id)
            return False

        return True

    async def revoke_token(self, token_id: str) -> bool:
        """Revoke a refresh token."""
        record = self._tokens.get(token_id)
        if not record:
            logger.warning("Token not found for revocation", token_id=token_id)
            return False

        record.revoked = True
        logger.info("Token revoked", token_id=token_id, user_id=record.user_id)
        return True

    async def revoke_user_tokens(self, user_id: str) -> int:
        """Revoke all refresh tokens for a user."""
        count = 0
        for record in self._tokens.values():
            if record.user_id == user_id and not record.revoked:
                record.revoked = True
                count += 1

        logger.info("User tokens revoked", user_id=user_id, count=count)
        return count

    async def cleanup_expired(self) -> int:
        """Remove expired tokens from storage."""
        now = datetime.utcnow()
        expired_ids = [
            token_id for token_id, record in self._tokens.items() if now > record.expires_at
        ]

        for token_id in expired_ids:
            del self._tokens[token_id]

        if expired_ids:
            logger.info("Expired tokens cleaned up", count=len(expired_ids))

        return len(expired_ids)

    def get_token_count(self) -> int:
        """Get total number of stored tokens (for monitoring)."""
        return len(self._tokens)

    def get_user_token_count(self, user_id: str) -> int:
        """Get number of tokens for a specific user."""
        return sum(1 for r in self._tokens.values() if r.user_id == user_id)


# Global token storage instance
_token_storage: InMemoryTokenStorage | None = None


def get_token_storage() -> InMemoryTokenStorage:
    """Get or create the global token storage instance.

    Reason: Lazy initialization and global singleton pattern.
    """
    global _token_storage
    if _token_storage is None:
        _token_storage = InMemoryTokenStorage()
        logger.info("Token storage initialized")
    return _token_storage


def reset_token_storage() -> None:
    """Reset token storage (for testing).

    Reason: Allows tests to start with clean state.
    """
    global _token_storage
    _token_storage = None
