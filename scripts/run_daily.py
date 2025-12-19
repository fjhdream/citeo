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
from citeo.notifiers import create_notifier
from citeo.parsers.arxiv_parser import ArxivParser
from citeo.services.paper_service import PaperService
from citeo.sources.arxiv import ArxivFeedSource
from citeo.storage import create_storage
from citeo.utils.logger import configure_logging, get_logger


async def main(fetch_only: bool = False):
    """Run the daily pipeline manually."""
    configure_logging(log_level=settings.log_level)
    logger = get_logger("run_daily")

    logger.info("Initializing components")

    # Initialize storage
    storage = create_storage(settings)
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

    # Create notifier(s)
    notifier = create_notifier(
        notifier_types=settings.notifier_types,
        telegram_token=(
            settings.telegram_bot_token.get_secret_value() if settings.telegram_bot_token else None
        ),
        telegram_chat_id=settings.telegram_chat_id,
        feishu_webhook_url=(
            settings.feishu_webhook_url.get_secret_value() if settings.feishu_webhook_url else None
        ),
        feishu_secret=(
            settings.feishu_secret.get_secret_value() if settings.feishu_secret else None
        ),
    )

    # Create service
    paper_service = PaperService(
        sources=sources,
        parser=parser,
        storage=storage,
        notifier=notifier,
        enable_translation=settings.enable_translation,
        max_concurrent_ai=settings.ai_max_concurrent,
        min_notification_score=settings.min_notification_score,
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
