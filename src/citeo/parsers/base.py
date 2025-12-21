"""Abstract feed parser interface using Protocol."""

from typing import Protocol

from citeo.models.paper import Paper


class FeedParser(Protocol):
    """RSS feed parser abstraction protocol."""

    def parse(self, raw_content: str, source_id: str) -> list[Paper]:
        """Parse RSS content into Paper objects.

        Args:
            raw_content: Raw XML string from feed source.
            source_id: Source identifier for metadata.

        Returns:
            List of parsed Paper objects.

        Raises:
            ParseError: When parsing fails.
        """
        ...
