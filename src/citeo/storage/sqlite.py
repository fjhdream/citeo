"""SQLite storage implementation for papers.

Provides async SQLite storage with deduplication and status tracking.
"""

import json
from datetime import datetime
from pathlib import Path

import aiosqlite

from citeo.models.paper import Paper, PaperSummary


class SQLitePaperStorage:
    """SQLite-based paper storage implementation.

    Reason: SQLite provides zero-deployment-cost persistence suitable
    for the expected data volume (tens to hundreds of papers per day).
    """

    def __init__(self, db_path: Path):
        """Initialize SQLite storage.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = db_path
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize database schema.

        Creates tables if they don't exist. Should be called once on startup.
        """
        if self._initialized:
            return

        # Ensure parent directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        # Load and execute schema
        schema_path = Path(__file__).parent / "migrations" / "init_schema.sql"
        schema_sql = schema_path.read_text()

        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(schema_sql)
            await db.commit()

        self._initialized = True

    async def save_paper(self, paper: Paper) -> bool:
        """Save paper, returns True if new (not duplicate).

        Reason: Using INSERT OR IGNORE for atomic deduplication.
        """
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
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
            await db.commit()
            return cursor.rowcount > 0

    async def get_paper_by_guid(self, guid: str) -> Paper | None:
        """Get paper by GUID."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM papers WHERE guid = ?", (guid,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_paper(row)
                return None

    async def get_paper_by_arxiv_id(self, arxiv_id: str) -> Paper | None:
        """Get paper by arXiv ID."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_paper(row)
                return None

    async def get_papers_by_date(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[Paper]:
        """Get papers within date range."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM papers
                WHERE published_at >= ? AND published_at <= ?
                ORDER BY published_at DESC
                """,
                (start_date.isoformat(), end_date.isoformat()),
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_paper(row) for row in rows]

    async def count_papers_by_date(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> int:
        """Count papers within date range.

        Reason: Efficient count query for pagination without loading all papers.
        """
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                """
                SELECT COUNT(*) FROM papers
                WHERE published_at >= ? AND published_at <= ?
                """,
                (start_date.isoformat(), end_date.isoformat()),
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_pending_papers(self) -> list[Paper]:
        """Get papers waiting for notification."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM papers
                WHERE is_notified = 0
                ORDER BY published_at ASC
                """
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_paper(row) for row in rows]

    async def mark_as_notified(self, guid: str) -> None:
        """Mark paper as notified."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                UPDATE papers
                SET is_notified = 1, notified_at = ?, updated_at = ?
                WHERE guid = ?
                """,
                (datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), guid),
            )
            await db.commit()

    async def update_summary(self, guid: str, summary: PaperSummary) -> None:
        """Update paper's AI-generated summary."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
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
            await db.commit()

    async def update_deep_analysis(self, guid: str, analysis: str) -> None:
        """Update paper's deep analysis result."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                UPDATE papers
                SET deep_analysis = ?, deep_analysis_at = ?, updated_at = ?
                WHERE guid = ?
                """,
                (analysis, datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), guid),
            )
            await db.commit()

    async def get_papers_by_fetched_date(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[Paper]:
        """Get papers by fetch date (not publish date).

        Reason: Used for manual daily task triggering to find papers
        fetched today, regardless of their publication date.
        """
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM papers
                WHERE fetched_at >= ? AND fetched_at < ?
                ORDER BY fetched_at DESC
                """,
                (start_date.isoformat(), end_date.isoformat()),
            ) as cursor:
                rows = await cursor.fetchall()
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
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                f"""
                UPDATE papers
                SET is_notified = 0, notified_at = NULL, updated_at = ?
                WHERE guid IN ({placeholders})
                """,
                (datetime.utcnow().isoformat(), *guids),
            )
            await db.commit()

    async def close(self) -> None:
        """Close storage (no-op for SQLite as we use connection per operation)."""
        pass

    def _row_to_paper(self, row: aiosqlite.Row) -> Paper:
        """Convert database row to Paper object."""
        summary = None
        if row["title_zh"]:
            summary = PaperSummary(
                title_zh=row["title_zh"],
                abstract_zh=row["abstract_zh"] or "",
                key_points=json.loads(row["key_points"] or "[]"),
                relevance_score=row["relevance_score"] or 0.0,
                deep_analysis=row["deep_analysis"],
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
                datetime.fromisoformat(row["notified_at"]) if row["notified_at"] else None
            ),
        )
