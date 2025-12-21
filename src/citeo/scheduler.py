"""Scheduler configuration using APScheduler.

Provides daily scheduled tasks for RSS fetching and processing.
"""

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from citeo.services.paper_service import PaperService

logger = structlog.get_logger()


def create_scheduler(
    paper_service: PaperService,
    hour: int = 8,
    minute: int = 0,
) -> AsyncIOScheduler:
    """Create and configure the task scheduler.

    Reason: Using factory function for dependency injection and testability.

    Args:
        paper_service: Paper service instance to use for daily pipeline.
        hour: Hour to run daily job (0-23).
        minute: Minute to run daily job (0-59).

    Returns:
        Configured AsyncIOScheduler.
    """
    scheduler = AsyncIOScheduler()

    # Add daily fetch job
    scheduler.add_job(
        paper_service.run_daily_pipeline,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="daily_rss_fetch",
        name="Daily RSS Fetch and Push",
        replace_existing=True,
        misfire_grace_time=3600,  # Allow 1 hour misfire grace
    )

    logger.info(
        "Scheduler configured",
        job_id="daily_rss_fetch",
        schedule=f"{hour:02d}:{minute:02d}",
    )

    return scheduler


async def run_once(paper_service: PaperService) -> dict:
    """Run the pipeline once immediately.

    Useful for manual triggers or testing.

    Args:
        paper_service: Paper service instance.

    Returns:
        Pipeline execution statistics.
    """
    logger.info("Running pipeline manually")
    return await paper_service.run_daily_pipeline()
