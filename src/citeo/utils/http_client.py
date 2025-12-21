"""HTTP client utilities.

Provides configured HTTP client with sensible defaults.
"""

import httpx


def create_http_client(
    timeout: int = 30,
    user_agent: str = "Citeo/1.0",
    follow_redirects: bool = True,
) -> httpx.AsyncClient:
    """Create a configured async HTTP client.

    Args:
        timeout: Request timeout in seconds.
        user_agent: User-Agent header value.
        follow_redirects: Whether to follow redirects.

    Returns:
        Configured httpx.AsyncClient.
    """
    return httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": user_agent},
        follow_redirects=follow_redirects,
    )


async def fetch_url(
    url: str,
    timeout: int = 30,
    headers: dict | None = None,
) -> str:
    """Fetch content from URL.

    Args:
        url: URL to fetch.
        timeout: Request timeout in seconds.
        headers: Optional additional headers.

    Returns:
        Response text content.

    Raises:
        httpx.HTTPError: On request failure.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.text
