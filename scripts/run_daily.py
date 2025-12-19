#!/usr/bin/env python
"""Script to manually trigger the daily pipeline.

Usage:
    python scripts/run_daily.py [--fetch-only]
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add src to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from citeo.config.settings import settings
from citeo.notifiers.telegram import TelegramNotifier
from citeo.parsers.arxiv_parser import ArxivParser
from citeo.services.paper_service import PaperService
from citeo.sources.arxiv import ArxivFeedSource
from citeo.storage.sqlite import SQLitePaperStorage
from citeo.utils.logger import configure_logging, get_logger


async def main(fetch_only: bool = False):
    """Run the daily pipeline manually."""
    configure_logging(log_level=settings.log_level)
    logger = get_logger("run_daily")

    logger.info("Initializing components")

    # Initialize storage
    storage = SQLitePaperStorage(settings.db_path)
    await storage.initialize()

    # Create sources
    sources = [
        ArxivFeedSource(
            url=url,
            timeout=settings.rss_fetch_timeout,
            user_agent=settings.rss_user_agent,
        )
        for url in settings.feed_urls
    ]

    # Create parser
    parser = ArxivParser()

    # Create notifier
    notifier = TelegramNotifier(
        token=settings.telegram_bot_token.get_secret_value(),
        chat_id=settings.telegram_chat_id,
    )

    # Create service
    paper_service = PaperService(
        sources=sources,
        parser=parser,
        storage=storage,
        notifier=notifier,
        enable_translation=settings.enable_translation,
    )

    # Run pipeline
    if fetch_only:
        logger.info("Running fetch-only mode")
        stats = await paper_service.fetch_only()
    else:
        logger.info("Running full pipeline")
        stats = await paper_service.run_daily_pipeline()

    # Cleanup
    await storage.close()

    # Print results
    logger.info("Pipeline completed", **stats)
    print("\nPipeline Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description="Run Citeo daily pipeline")
    arg_parser.add_argument(
        "--fetch-only",
        action="store_true",
        help="Only fetch papers, skip AI processing and notifications",
    )
    args = arg_parser.parse_args()

    asyncio.run(main(fetch_only=args.fetch_only))
