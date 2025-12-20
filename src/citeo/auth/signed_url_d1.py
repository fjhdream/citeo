"""D1 implementation of nonce storage for signed URLs.

Provides nonce tracking using Cloudflare D1 database.
"""

import time

import httpx
import structlog

logger = structlog.get_logger()


class D1NonceStorage:
    """Manage one-time-use nonce state with Cloudflare D1 storage.

    Reason: Store nonce state in D1 to track used nonces and prevent
    replay attacks when using D1 as the main database.
    """

    def __init__(self, account_id: str, database_id: str, api_token: str | None):
        """Initialize D1 nonce storage.

        Args:
            account_id: Cloudflare account ID.
            database_id: D1 database ID.
            api_token: Cloudflare API token with D1 permissions.
        """
        self._account_id = account_id
        self._database_id = database_id
        self._api_token = api_token
        self._base_url = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/"
            f"d1/database/{database_id}/query"
        )

    async def _execute_query(self, sql: str, params: list | None = None) -> dict:
        """Execute SQL query against D1 database.

        Args:
            sql: SQL query string.
            params: Query parameters.

        Returns:
            Query result from D1 API.

        Raises:
            httpx.HTTPError: If API request fails.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "sql": sql,
                    "params": params or [],
                },
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("success"):
                errors = data.get("errors", [])
                error_msg = errors[0].get("message") if errors else "Unknown error"
                raise RuntimeError(f"D1 query failed: {error_msg}")

            return data.get("result", [{}])[0]

    async def _init_table(self) -> None:
        """Create nonce table if it doesn't exist."""
        try:
            await self._execute_query(
                """
                CREATE TABLE IF NOT EXISTS signed_url_nonces (
                    nonce TEXT PRIMARY KEY,
                    created_at INTEGER NOT NULL,
                    consumed_at INTEGER,
                    arxiv_id TEXT NOT NULL,
                    platform TEXT NOT NULL
                )
                """
            )

            # Create index for cleanup queries
            await self._execute_query(
                """
                CREATE INDEX IF NOT EXISTS idx_nonces_created_at
                ON signed_url_nonces(created_at)
                """
            )

            logger.debug("D1 nonce table initialized")

        except Exception as e:
            logger.error("Failed to initialize D1 nonce table", error=str(e))
            raise

    async def is_nonce_used(self, nonce: str) -> bool:
        """Check if a nonce has been used.

        Args:
            nonce: The nonce to check.

        Returns:
            True if nonce exists (already used), False otherwise.
        """
        await self._init_table()

        try:
            result = await self._execute_query(
                "SELECT consumed_at FROM signed_url_nonces WHERE nonce = ?",
                [nonce],
            )

            # Check if result has rows
            results = result.get("results", [])
            return len(results) > 0

        except Exception as e:
            logger.error("Failed to check nonce", nonce=nonce, error=str(e))
            # Fail safe: assume nonce is used to prevent replay
            return True

    async def mark_nonce_used(self, nonce: str, arxiv_id: str, platform: str) -> bool:
        """Mark a nonce as used.

        Args:
            nonce: The nonce to mark as used.
            arxiv_id: Associated arXiv paper ID.
            platform: Platform that triggered the request.

        Returns:
            True if successfully marked, False if already exists.
        """
        await self._init_table()

        now = int(time.time())

        try:
            await self._execute_query(
                """
                INSERT INTO signed_url_nonces
                (nonce, created_at, consumed_at, arxiv_id, platform)
                VALUES (?, ?, ?, ?, ?)
                """,
                [nonce, now, now, arxiv_id, platform],
            )
            return True

        except Exception as e:
            # Check if it's a constraint violation (nonce already exists)
            error_msg = str(e)
            if "UNIQUE constraint" in error_msg or "PRIMARY KEY" in error_msg:
                logger.warning("Nonce already used", nonce=nonce)
                return False

            logger.error("Failed to mark nonce as used", nonce=nonce, error=error_msg)
            return False

    async def cleanup_expired_nonces(self, expiry_hours: int = 168) -> int:
        """Remove expired nonces from storage.

        Args:
            expiry_hours: Nonces older than this are deleted (default: 7 days).

        Returns:
            Number of nonces deleted.
        """
        await self._init_table()

        cutoff = int(time.time()) - (expiry_hours * 3600)

        try:
            result = await self._execute_query(
                "DELETE FROM signed_url_nonces WHERE created_at < ?",
                [cutoff],
            )

            # D1 returns meta with changes count
            deleted = result.get("meta", {}).get("changes", 0)

            if deleted > 0:
                logger.info("Cleaned up expired nonces", count=deleted)

            return deleted

        except Exception as e:
            logger.error("Failed to cleanup nonces", error=str(e))
            return 0
