"""Simple in-memory rate limiter for API endpoints.

Reason: Protects expensive /analyze endpoint from abuse.
For production, consider Redis-based implementation.
"""

import time
from collections import defaultdict
from dataclasses import dataclass

import structlog

from citeo.auth.exceptions import RateLimitExceededError

logger = structlog.get_logger()


@dataclass
class RateLimitConfig:
    """Rate limit configuration.

    Attributes:
        requests: Maximum requests allowed in window.
        window_seconds: Time window in seconds.
    """

    requests: int = 10
    window_seconds: int = 60


class InMemoryRateLimiter:
    """Simple in-memory sliding window rate limiter.

    Reason: Good enough for single-instance deployment.
    Not suitable for multi-instance (use Redis in that case).

    Note: This implementation uses a simple sliding window log approach.
    """

    def __init__(self, config: RateLimitConfig | None = None):
        """Initialize rate limiter.

        Args:
            config: Rate limit configuration. Defaults to 10 requests/minute.
        """
        self.config = config or RateLimitConfig()
        # Dict of identifier -> list of request timestamps
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check_rate_limit(self, identifier: str) -> None:
        """Check if request is within rate limit.

        Args:
            identifier: Unique identifier (e.g., user_id, IP address).

        Raises:
            RateLimitExceededError: If rate limit exceeded.
        """
        now = time.time()
        window_start = now - self.config.window_seconds

        # Get request timestamps for this identifier
        request_times = self._requests[identifier]

        # Remove expired timestamps (outside window)
        request_times[:] = [t for t in request_times if t > window_start]

        # Check if over limit
        if len(request_times) >= self.config.requests:
            # Calculate retry-after
            oldest_in_window = min(request_times)
            retry_after = int(oldest_in_window + self.config.window_seconds - now) + 1
            logger.warning(
                "Rate limit exceeded",
                identifier=identifier,
                requests=len(request_times),
                limit=self.config.requests,
            )
            raise RateLimitExceededError(retry_after=retry_after)

        # Record this request
        request_times.append(now)

    def get_remaining(self, identifier: str) -> int:
        """Get remaining requests in current window.

        Args:
            identifier: Unique identifier.

        Returns:
            Number of remaining requests allowed.
        """
        now = time.time()
        window_start = now - self.config.window_seconds
        request_times = self._requests.get(identifier, [])
        current_count = sum(1 for t in request_times if t > window_start)
        return max(0, self.config.requests - current_count)

    def reset(self, identifier: str | None = None) -> None:
        """Reset rate limit counters.

        Args:
            identifier: Specific identifier to reset. If None, resets all.
        """
        if identifier:
            self._requests.pop(identifier, None)
        else:
            self._requests.clear()


# Global rate limiter for /analyze endpoint
_analyze_rate_limiter: InMemoryRateLimiter | None = None


def get_analyze_rate_limiter() -> InMemoryRateLimiter:
    """Get rate limiter for /analyze endpoint.

    Reason: Lazy initialization with settings-based configuration.
    """
    global _analyze_rate_limiter
    if _analyze_rate_limiter is None:
        from citeo.config.settings import settings

        _analyze_rate_limiter = InMemoryRateLimiter(
            RateLimitConfig(
                requests=settings.rate_limit_analyze_requests,
                window_seconds=settings.rate_limit_analyze_window,
            )
        )
    return _analyze_rate_limiter
