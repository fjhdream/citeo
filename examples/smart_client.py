"""Smart Citeo API client with automatic token management.

Handles the complete token lifecycle:
1. Initial login with API key
2. Automatic token refresh before expiry
3. Fallback to API key if refresh token expires
"""

from datetime import datetime, timedelta

import httpx


class CiteoClient:
    """Intelligent Citeo API client with automatic token management."""

    def __init__(self, base_url: str, api_key: str):
        """Initialize client.

        Args:
            base_url: API base URL (e.g., http://localhost:8000)
            api_key: Your API key for authentication
        """
        self.base_url = base_url
        self.api_key = api_key
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.token_expires_at: datetime | None = None

    def _is_token_expired(self) -> bool:
        """Check if access token has expired or will expire soon.

        Returns:
            True if token is expired or will expire within 5 minutes.
        """
        if not self.token_expires_at:
            return True
        # Refresh 5 minutes before expiry
        return datetime.now() >= self.token_expires_at - timedelta(minutes=5)

    def login(self) -> dict:
        """Login with API key to get initial token pair.

        Returns:
            Token response with access_token, refresh_token, expires_in.

        Raises:
            httpx.HTTPError: If login fails.
        """
        response = httpx.post(
            f"{self.base_url}/api/auth/token",
            json={"api_key": self.api_key},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()

        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.token_expires_at = datetime.now() + timedelta(seconds=data["expires_in"])

        print(f"✓ Logged in successfully, token expires at {self.token_expires_at}")
        return data

    def refresh_tokens(self) -> dict:
        """Refresh tokens using refresh token.

        Returns:
            Token response with new tokens.

        Raises:
            httpx.HTTPError: If refresh fails (e.g., token expired).
        """
        if not self.refresh_token:
            raise ValueError("No refresh token available, must login first")

        try:
            response = httpx.post(
                f"{self.base_url}/api/auth/refresh",
                json={"refresh_token": self.refresh_token},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

            self.access_token = data["access_token"]
            self.refresh_token = data["refresh_token"]
            self.token_expires_at = datetime.now() + timedelta(seconds=data["expires_in"])

            print(f"✓ Tokens refreshed, new token expires at {self.token_expires_at}")
            return data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                # Refresh token expired or invalid
                print("⚠ Refresh token expired, logging in with API key...")
                return self.login()
            raise

    def ensure_valid_token(self) -> None:
        """Ensure we have a valid access token.

        This method handles the complete token lifecycle:
        1. If no token, login with API key
        2. If token expired, try to refresh
        3. If refresh fails, login with API key
        """
        if not self.access_token:
            print("No token found, logging in...")
            self.login()
        elif self._is_token_expired():
            print("Token expired or expiring soon, refreshing...")
            try:
                self.refresh_tokens()
            except httpx.HTTPError as e:
                print(f"⚠ Refresh failed: {e}, logging in with API key...")
                self.login()

    def api_call(self, endpoint: str, method: str = "GET", **kwargs) -> dict:
        """Make an API call with automatic token management.

        Args:
            endpoint: API endpoint (e.g., /api/papers/by-date)
            method: HTTP method (GET, POST, etc.)
            **kwargs: Additional arguments for httpx.request

        Returns:
            API response as JSON.

        Raises:
            httpx.HTTPError: If API call fails.
        """
        self.ensure_valid_token()

        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.access_token}"

        response = httpx.request(
            method,
            f"{self.base_url}{endpoint}",
            headers=headers,
            timeout=10.0,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()

    def get_papers_by_date(self, date: str | None = None, limit: int = 20) -> dict:
        """Get papers by date.

        Args:
            date: Date in YYYY-MM-DD format, defaults to today.
            limit: Number of papers to return.

        Returns:
            Papers list response.
        """
        params = {"limit": limit}
        if date:
            params["date"] = date

        return self.api_call("/api/papers/by-date", params=params)

    def analyze_paper(self, arxiv_id: str, sync: bool = False) -> dict:
        """Trigger paper analysis.

        Args:
            arxiv_id: arXiv paper ID.
            sync: Whether to wait for analysis completion.

        Returns:
            Analysis response.
        """
        params = {"sync": sync}
        return self.api_call(f"/api/papers/{arxiv_id}/analyze", method="POST", params=params)

    def logout(self) -> None:
        """Logout by revoking the refresh token.

        After logout, you need to call login() again to use the client.
        """
        if self.refresh_token:
            try:
                response = httpx.post(
                    f"{self.base_url}/api/auth/revoke",
                    json={"token": self.refresh_token},
                    timeout=10.0,
                )
                response.raise_for_status()
                print("✓ Logged out successfully")
            except httpx.HTTPError as e:
                print(f"⚠ Logout failed: {e}")

        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = None


# ============= Usage Examples =============


def example_basic_usage():
    """Example: Basic API usage with automatic token management."""
    client = CiteoClient("http://localhost:8000", "your-api-key")

    # First call - will automatically login
    papers = client.get_papers_by_date()
    print(f"Found {papers['count']} papers")

    # Subsequent calls - reuses existing token
    for _ in range(10):
        papers = client.get_papers_by_date()
        # Token is automatically refreshed if needed

    # Logout when done
    client.logout()


def example_long_running():
    """Example: Long-running application (e.g., daemon)."""
    import time

    client = CiteoClient("http://localhost:8000", "your-api-key")

    # Run for days - tokens are automatically managed
    while True:
        try:
            papers = client.get_papers_by_date()
            print(f"Checked at {datetime.now()}: {papers['count']} papers")

            # Sleep for 1 hour
            time.sleep(3600)

        except KeyboardInterrupt:
            print("Shutting down...")
            client.logout()
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)  # Wait 1 minute before retry


def example_error_handling():
    """Example: Robust error handling."""
    client = CiteoClient("http://localhost:8000", "your-api-key")

    try:
        # This will handle all token management automatically
        papers = client.get_papers_by_date()
        print(f"Success: {papers['count']} papers")

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            print("Authentication failed - check your API key")
        else:
            print(f"HTTP error: {e}")

    except httpx.RequestError as e:
        print(f"Network error: {e}")

    finally:
        client.logout()


if __name__ == "__main__":
    print("=" * 60)
    print("Citeo Smart Client Examples")
    print("=" * 60)

    # Uncomment to run examples:
    # example_basic_usage()
    # example_long_running()
    # example_error_handling()

    print("\nUsage:")
    print("  client = CiteoClient('http://localhost:8000', 'your-api-key')")
    print("  papers = client.get_papers_by_date()")
    print("  # Tokens are managed automatically!")
