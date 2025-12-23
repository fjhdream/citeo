"""Cloudflare D1 storage implementation for papers.

Provides async D1 storage using Cloudflare REST API.
"""

import json
from datetime import datetime
from pathlib import Path

import httpx
import structlog

from citeo.models.paper import Paper, PaperSummary

logger = structlog.get_logger()


class D1PaperStorage:
    """Cloudflare D1-based paper storage implementation.

    Reason: D1 is a globally distributed SQLite database offering
    edge-deployed storage with low latency worldwide.
    Uses Cloudflare REST API for database operations.
    """

    def __init__(
        self,
        account_id: str,
        database_id: str,
        api_token: str,
    ):
        """Initialize D1 storage.

        Args:
            account_id: Cloudflare account ID.
            database_id: D1 database ID.
            api_token: Cloudflare API token with D1 read/write permissions.
        """
        self._account_id = account_id
        self._database_id = database_id
        self._api_token = api_token
        self._base_url = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
            f"/d1/database/{database_id}"
        )
        self._initialized = False
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self._api_token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def _execute(self, sql: str, params: tuple = ()) -> dict:
        """Execute a SQL statement on D1.

        Args:
            sql: SQL statement to execute.
            params: Query parameters (tuple).

        Returns:
            D1 API response dict.

        Raises:
            Exception: If D1 API returns an error.
        """
        client = await self._get_client()

        # Reason: D1 REST API accepts SQL with positional parameters
        payload = {"sql": sql}
        if params:
            payload["params"] = list(params)

        try:
            response = await client.post(
                f"{self._base_url}/query",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("success"):
                errors = data.get("errors", [])
                error_msg = errors[0].get("message") if errors else "Unknown error"
                raise Exception(f"D1 query failed: {error_msg}")

            return data.get("result", [])[0] if data.get("result") else {}

        except httpx.HTTPError as e:
            logger.error("D1 HTTP error", error=str(e))
            raise

    async def _execute_script(self, sql: str) -> None:
        """Execute a SQL script (multiple statements).

        Args:
            sql: SQL script with multiple statements.
        """
        # Reason: Split script into individual statements for D1 API
        statements = [s.strip() for s in sql.split(";") if s.strip()]

        for statement in statements:
            if statement:
                await self._execute(statement)

    async def initialize(self) -> None:
        """Initialize database schema.

        Creates tables if they don't exist. Should be called once on startup.
        """
        if self._initialized:
            return

        # Load and execute schema
        schema_path = Path(__file__).parent / "migrations" / "init_schema.sql"
        schema_sql = schema_path.read_text()

        await self._execute_script(schema_sql)

        self._initialized = True
        logger.info("D1 storage initialized")

    async def save_paper(self, paper: Paper) -> bool:
        """Save paper, returns True if new (not duplicate).

        Reason: Using INSERT OR IGNORE for atomic deduplication.
        """
        result = await self._execute(
            """
            INSERT OR IGNORE INTO papers (
                guid, arxiv_id, title, abstract, authors,
                categories, announce_type, published_at,
                abs_url, source_id, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paper.guid,
                paper.arxiv_id,
                paper.title,
                paper.abstract,
                json.dumps(paper.authors),
                json.dumps(paper.categories),
                paper.announce_type,
                paper.published_at.isoformat(),
                paper.abs_url,
                paper.source_id,
                paper.fetched_at.isoformat(),
            ),
        )

        # Reason: D1 returns meta.changes to indicate rows affected
        return result.get("meta", {}).get("changes", 0) > 0

    async def get_paper_by_guid(self, guid: str) -> Paper | None:
        """Get paper by GUID."""
        result = await self._execute("SELECT * FROM papers WHERE guid = ?", (guid,))

        rows = result.get("results", [])
        if rows:
            return self._row_to_paper(rows[0])
        return None

    async def get_paper_by_arxiv_id(self, arxiv_id: str) -> Paper | None:
        """Get paper by arXiv ID."""
        result = await self._execute("SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,))

        rows = result.get("results", [])
        if rows:
            return self._row_to_paper(rows[0])
        return None

    async def get_papers_by_date(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[Paper]:
        """Get papers within date range."""
        result = await self._execute(
            """
            SELECT * FROM papers
            WHERE published_at >= ? AND published_at <= ?
            ORDER BY published_at DESC
            """,
            (start_date.isoformat(), end_date.isoformat()),
        )

        rows = result.get("results", [])
        return [self._row_to_paper(row) for row in rows]

    async def count_papers_by_date(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> int:
        """Count papers within date range.

        Reason: Efficient count query for pagination without loading all papers.
        """
        result = await self._execute(
            """
            SELECT COUNT(*) as count FROM papers
            WHERE published_at >= ? AND published_at <= ?
            """,
            (start_date.isoformat(), end_date.isoformat()),
        )

        rows = result.get("results", [])
        return rows[0]["count"] if rows else 0

    async def get_pending_papers(self) -> list[Paper]:
        """Get papers waiting for notification."""
        result = await self._execute(
            """
            SELECT * FROM papers
            WHERE is_notified = 0
            ORDER BY published_at ASC
            """
        )

        rows = result.get("results", [])
        return [self._row_to_paper(row) for row in rows]

    async def mark_as_notified(self, guid: str) -> None:
        """Mark paper as notified."""
        await self._execute(
            """
            UPDATE papers
            SET is_notified = 1, notified_at = ?, updated_at = ?
            WHERE guid = ?
            """,
            (datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), guid),
        )

    async def update_summary(self, guid: str, summary: PaperSummary) -> None:
        """Update paper's AI-generated summary."""
        await self._execute(
            """
            UPDATE papers
            SET title_zh = ?, abstract_zh = ?, key_points = ?,
                relevance_score = ?, ai_processed_at = ?, updated_at = ?
            WHERE guid = ?
            """,
            (
                summary.title_zh,
                summary.abstract_zh,
                json.dumps(summary.key_points),
                summary.relevance_score,
                summary.generated_at.isoformat(),
                datetime.utcnow().isoformat(),
                guid,
            ),
        )

    async def update_deep_analysis(self, guid: str, analysis: str) -> None:
        """Update paper's deep analysis result."""
        await self._execute(
            """
            UPDATE papers
            SET deep_analysis = ?, deep_analysis_at = ?, updated_at = ?
            WHERE guid = ?
            """,
            (analysis, datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), guid),
        )

    async def get_papers_by_fetched_date(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[Paper]:
        """Get papers by fetch date (not publish date).

        Reason: Used for manual daily task triggering to find papers
        fetched today, regardless of their publication date.
        """
        result = await self._execute(
            """
            SELECT * FROM papers
            WHERE fetched_at >= ? AND fetched_at < ?
            ORDER BY fetched_at DESC
            """,
            (start_date.isoformat(), end_date.isoformat()),
        )

        rows = result.get("results", [])
        return [self._row_to_paper(row) for row in rows]

    async def reset_notification_status(self, guids: list[str]) -> None:
        """Reset notification status for re-sending.

        Reason: Allows force re-notification of papers that were
        already sent, useful for manual testing or corrections.
        """
        if not guids:
            return

        # Reason: Build parameterized query to avoid SQL injection
        placeholders = ",".join("?" * len(guids))
        await self._execute(
            f"""
            UPDATE papers
            SET is_notified = 0, notified_at = NULL, updated_at = ?
            WHERE guid IN ({placeholders})
            """,
            (datetime.utcnow().isoformat(), *guids),
        )

    async def close(self) -> None:
        """Close storage connection."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _row_to_paper(self, row: dict) -> Paper:
        """Convert D1 result row to Paper object.

        Reason: D1 REST API returns results as list of dicts,
        unlike aiosqlite which returns Row objects.
        """
        summary = None
        if row.get("title_zh"):
            summary = PaperSummary(
                title_zh=row["title_zh"],
                abstract_zh=row.get("abstract_zh") or "",
                key_points=json.loads(row.get("key_points") or "[]"),
                relevance_score=row.get("relevance_score") or 0.0,
                deep_analysis=row.get("deep_analysis"),
            )

        return Paper(
            guid=row["guid"],
            arxiv_id=row["arxiv_id"],
            title=row["title"],
            abstract=row["abstract"],
            authors=json.loads(row["authors"]),
            categories=json.loads(row["categories"]),
            announce_type=row["announce_type"],
            published_at=datetime.fromisoformat(row["published_at"]),
            abs_url=row["abs_url"],
            source_id=row["source_id"],
            fetched_at=datetime.fromisoformat(row["fetched_at"]),
            summary=summary,
            is_notified=bool(row["is_notified"]),
            notified_at=(
                datetime.fromisoformat(row["notified_at"]) if row.get("notified_at") else None
            ),
        )
