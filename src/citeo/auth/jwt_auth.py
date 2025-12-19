"""JWT authenticator implementation with token utilities.

Reason: Using PyJWT for JWT operations, which is a lightweight
and well-maintained library.
"""

import secrets
from datetime import datetime, timedelta

import jwt
import structlog

from citeo.auth.exceptions import TokenExpiredError
from citeo.auth.models import AuthUser, TokenPayload

logger = structlog.get_logger()

# JWT algorithm - HS256 is appropriate for single-user scenarios
ALGORITHM = "HS256"


def generate_token_id() -> str:
    """Generate a unique token ID (jti claim).

    Returns:
        Random URL-safe token ID.

    Reason: Used to uniquely identify tokens for revocation.
    """
    return secrets.token_urlsafe(32)


def create_access_token(
    secret_key: str,
    expires_delta: timedelta | None = None,
    subject: str = "default",
) -> str:
    """Create a new JWT access token.

    Args:
        secret_key: Secret key for signing the token.
        expires_delta: Token validity duration. Defaults to 1 hour.
        subject: User identifier to encode in token.

    Returns:
        Encoded JWT string.

    Reason: Access tokens are short-lived and don't need jti for revocation.
    Use refresh tokens for long-term authentication with revocation support.
    """
    if expires_delta is None:
        expires_delta = timedelta(hours=1)

    now = datetime.utcnow()
    expire = now + expires_delta

    payload = {
        "sub": subject,
        "exp": expire,
        "iat": now,
        "type": "access",
    }

    token = jwt.encode(payload, secret_key, algorithm=ALGORITHM)
    logger.debug("Access token created", expires_at=expire.isoformat())
    return token


def create_refresh_token(
    secret_key: str,
    expires_delta: timedelta | None = None,
    subject: str = "default",
) -> tuple[str, str, datetime]:
    """Create a new JWT refresh token.

    Args:
        secret_key: Secret key for signing the token.
        expires_delta: Token validity duration. Defaults to 7 days.
        subject: User identifier to encode in token.

    Returns:
        Tuple of (encoded JWT string, token_id, expiration datetime).

    Reason: Refresh tokens always include jti for revocation tracking.
    """
    if expires_delta is None:
        expires_delta = timedelta(days=7)

    now = datetime.utcnow()
    expire = now + expires_delta
    token_id = generate_token_id()

    payload = {
        "sub": subject,
        "exp": expire,
        "iat": now,
        "type": "refresh",
        "jti": token_id,
    }

    token = jwt.encode(payload, secret_key, algorithm=ALGORITHM)
    logger.debug(
        "Refresh token created",
        expires_at=expire.isoformat(),
        token_id=token_id,
    )
    return token, token_id, expire


def decode_token(token: str, secret_key: str) -> TokenPayload | None:
    """Decode and validate a JWT token.

    Args:
        token: The JWT string to decode.
        secret_key: Secret key used for signing.

    Returns:
        TokenPayload if valid, None if invalid.

    Raises:
        TokenExpiredError: If token has expired.
    """
    try:
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])

        # Extract jti if present
        jti = payload.get("jti")

        token_payload = TokenPayload(
            sub=payload.get("sub", "default"),
            exp=datetime.fromtimestamp(payload["exp"]),
            iat=datetime.fromtimestamp(payload.get("iat", datetime.utcnow().timestamp())),
            type=payload.get("type", "access"),
        )

        # Add jti to payload if present
        if jti:
            token_payload.jti = jti

        return token_payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token expired")
        raise TokenExpiredError()
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid JWT token", error=str(e))
        return None


class JWTAuthenticator:
    """JWT Bearer token authenticator.

    Reason: Stateless authentication suitable for API clients
    that can manage token lifecycle.
    """

    def __init__(self, secret_key: str):
        """Initialize with JWT secret key.

        Args:
            secret_key: Secret key for JWT signing/verification.
        """
        self._secret_key = secret_key

    async def authenticate(
        self,
        api_key: str | None = None,
        bearer_token: str | None = None,
    ) -> AuthUser | None:
        """Authenticate using JWT bearer token.

        Args:
            api_key: Ignored by this authenticator.
            bearer_token: JWT token from Authorization header.

        Returns:
            AuthUser if token is valid, None otherwise.
        """
        if not bearer_token:
            return None

        try:
            payload = decode_token(bearer_token, self._secret_key)
            if payload:
                logger.debug("JWT authentication successful", subject=payload.sub)
                return AuthUser(user_id=payload.sub, auth_method="jwt")
        except TokenExpiredError:
            # Re-raise to allow proper 401 response with specific message
            raise

        return None

    def validate_credentials(self) -> bool:
        """Check if secret key is configured."""
        return bool(self._secret_key and len(self._secret_key) >= 32)

    def create_token(
        self,
        expires_delta: timedelta | None = None,
        subject: str = "default",
    ) -> str:
        """Create a new access token.

        Convenience method wrapping the module-level function.
        """
        return create_access_token(
            secret_key=self._secret_key,
            expires_delta=expires_delta,
            subject=subject,
        )
