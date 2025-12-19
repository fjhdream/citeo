"""Authentication-specific exceptions.

Extends the Citeo exception hierarchy for auth errors.
"""

from citeo.exceptions import CiteoError


class AuthenticationError(CiteoError):
    """Base authentication error."""

    pass


class InvalidCredentialsError(AuthenticationError):
    """Raised when credentials are invalid or missing.

    Attributes:
        auth_method: The authentication method that failed.
    """

    def __init__(self, auth_method: str, message: str = "Invalid credentials"):
        self.auth_method = auth_method
        super().__init__(f"Authentication failed ({auth_method}): {message}")


class TokenExpiredError(AuthenticationError):
    """Raised when JWT token has expired."""

    def __init__(self) -> None:
        super().__init__("Token has expired")


class RateLimitExceededError(AuthenticationError):
    """Raised when rate limit is exceeded.

    Attributes:
        retry_after: Seconds until rate limit resets.
    """

    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after} seconds")
