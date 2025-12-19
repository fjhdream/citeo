"""arXiv RSS feed source implementation."""

import httpx

from citeo.exceptions import FetchError


class ArxivFeedSource:
    """arXiv RSS feed source.

    Fetches RSS content from arXiv.org for a specific category.
    """

    def __init__(
        self,
        url: str,
        source_id: str | None = None,
        name: str | None = None,
        timeout: int = 30,
        user_agent: str = "Citeo/1.0 (arXiv RSS Reader)",
    ):
        """Initialize arXiv feed source.

        Args:
            url: RSS feed URL (e.g., https://rss.arxiv.org/rss/cs.AI).
            source_id: Unique source identifier. Defaults to URL-derived ID.
            name: Human-readable name. Defaults to source_id.
            timeout: Request timeout in seconds.
            user_agent: User-Agent header for requests.
        """
        self._url = url
        self._source_id = source_id or self._derive_source_id(url)
        self._name = name or self._source_id
        self._timeout = timeout
        self._user_agent = user_agent

    @property
    def source_id(self) -> str:
        """Unique identifier for this feed source."""
        return self._source_id

    @property
    def name(self) -> str:
        """Human-readable name for this source."""
        return self._name

    @property
    def url(self) -> str:
        """RSS feed URL."""
        return self._url

    async def fetch_raw(self) -> str:
        """Fetch raw RSS XML content from arXiv.

        Returns:
            Raw XML string.

        Raises:
            FetchError: When request fails or returns non-200 status.
        """
        headers = {"User-Agent": self._user_agent}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(self._url, headers=headers)
                response.raise_for_status()
                return response.text
        except httpx.TimeoutException as e:
            raise FetchError(self._source_id, f"Request timed out: {e}") from e
        except httpx.HTTPStatusError as e:
            raise FetchError(
                self._source_id, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            ) from e
        except httpx.RequestError as e:
            raise FetchError(self._source_id, f"Request failed: {e}") from e

    def _derive_source_id(self, url: str) -> str:
        """Derive source_id from URL.

        Example: https://rss.arxiv.org/rss/cs.AI -> arxiv.cs.AI
        """
        # Extract category from URL like /rss/cs.AI
        parts = url.rstrip("/").split("/")
        if len(parts) >= 2:
            category = parts[-1]  # e.g., "cs.AI"
            return f"arxiv.{category}"
        return "arxiv.unknown"
