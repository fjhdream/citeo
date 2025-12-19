"""Database migration script: Update scoring system from 0-1 to 1-10 scale.

This script updates existing relevance_score values in the database
from the old 0-1 range to the new 1-10 programmer recommendation scale.
"""

import asyncio
import sys
from pathlib import Path

import aiosqlite
import structlog

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from citeo.config.settings import settings

logger = structlog.get_logger()


async def migrate_scoring_system():
    """Migrate existing relevance scores from 0-1 to 1-10 scale."""
    db_path = settings.db_path
    log = logger.bind(db_path=db_path)

    log.info("Starting scoring system migration")

    async with aiosqlite.connect(db_path) as db:
        # Check current score range
        async with db.execute(
            "SELECT MIN(relevance_score), MAX(relevance_score), COUNT(*) FROM papers WHERE relevance_score > 0"
        ) as cursor:
            row = await cursor.fetchone()
            min_score, max_score, count = row if row else (None, None, 0)

        if count == 0:
            log.info("No papers with scores found, nothing to migrate")
            return

        log.info(
            "Current score range",
            min_score=min_score,
            max_score=max_score,
            papers_with_scores=count,
        )

        # Check if already migrated
        if max_score and max_score > 1.0:
            log.info("Scores already in 1-10 range, skipping migration")
            return

        # Run migration
        log.info("Updating scores from 0-1 to 1-10 scale")

        # Formula: new_score = old_score * 9 + 1
        # Reason: Maps 0.0->1.0, 0.5->5.5, 0.8->8.2, 1.0->10.0
        await db.execute(
            """
            UPDATE papers
            SET relevance_score = (relevance_score * 9.0) + 1.0
            WHERE relevance_score >= 0.0 AND relevance_score <= 1.0
            """
        )
        await db.commit()

        # Verify migration
        async with db.execute(
            "SELECT MIN(relevance_score), MAX(relevance_score), COUNT(*) FROM papers WHERE relevance_score >= 1.0"
        ) as cursor:
            row = await cursor.fetchone()
            new_min, new_max, new_count = row if row else (None, None, 0)

        log.info(
            "Migration completed",
            new_min_score=new_min,
            new_max_score=new_max,
            papers_updated=new_count,
        )


if __name__ == "__main__":
    asyncio.run(migrate_scoring_system())
