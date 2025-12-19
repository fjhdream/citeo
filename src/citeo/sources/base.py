"""Abstract feed source interface using Protocol."""

from typing import Protocol


class FeedSource(Protocol):
    """RSS feed source abstraction protocol.

    Reason: Using Protocol instead of ABC allows more flexible implementations
    while maintaining strict type checking.
    """

    @property
    def source_id(self) -> str:
        """Unique identifier for this feed source."""
        ...

    @property
    def name(self) -> str:
        """Human-readable name for this source."""
        ...

    async def fetch_raw(self) -> str:
        """Fetch raw RSS XML content.

        Returns:
            str: Raw XML string.

        Raises:
            FetchError: When network request fails.
        """
        ...
