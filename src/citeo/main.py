"""Main application entry point.

Initializes all components and starts the application with
scheduler and optional API server.
"""

import argparse
import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from citeo.config.settings import settings
from citeo.api import init_services, router
from citeo.notifiers.telegram import TelegramNotifier
from citeo.parsers.arxiv_parser import ArxivParser
from citeo.scheduler import create_scheduler, run_once
from citeo.services.paper_service import PaperService
from citeo.sources.arxiv import ArxivFeedSource
from citeo.storage.sqlite import SQLitePaperStorage
from citeo.utils.logger import configure_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    Handles startup and shutdown of scheduler and services.
    """
    logger = get_logger("lifespan")
    logger.info("Starting Citeo application")

    # Initialize storage
    storage = SQLitePaperStorage(settings.db_path)
    await storage.initialize()
    logger.info("Storage initialized", db_path=str(settings.db_path))

    # Initialize API services
    init_services(settings.db_path)

    # Create paper service
    sources = [
        ArxivFeedSource(
            url=url,
            timeout=settings.rss_fetch_timeout,
            user_agent=settings.rss_user_agent,
        )
        for url in settings.feed_urls
    ]
    parser = ArxivParser()
    notifier = TelegramNotifier(
        token=settings.telegram_bot_token.get_secret_value(),
        chat_id=settings.telegram_chat_id,
    )
    paper_service = PaperService(
        sources=sources,
        parser=parser,
        storage=storage,
        notifier=notifier,
        enable_translation=settings.enable_translation,
    )

    # Create and start scheduler
    scheduler = create_scheduler(
        paper_service,
        hour=settings.daily_fetch_hour,
        minute=settings.daily_fetch_minute,
    )
    scheduler.start()
    logger.info("Scheduler started")

    # Store in app state for access in routes
    app.state.paper_service = paper_service
    app.state.storage = storage
    app.state.scheduler = scheduler

    yield

    # Shutdown
    scheduler.shutdown()
    await storage.close()
    logger.info("Citeo application stopped")


def create_app() -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(
        title="Citeo API",
        description="arXiv RSS subscription with AI summarization",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


async def run_cli_once():
    """Run pipeline once via CLI without API server."""
    logger = get_logger("cli")
    logger.info("Running one-time pipeline")

    # Initialize components
    storage = SQLitePaperStorage(settings.db_path)
    await storage.initialize()

    sources = [
        ArxivFeedSource(
            url=url,
            timeout=settings.rss_fetch_timeout,
            user_agent=settings.rss_user_agent,
        )
        for url in settings.feed_urls
    ]
    parser = ArxivParser()
    notifier = TelegramNotifier(
        token=settings.telegram_bot_token.get_secret_value(),
        chat_id=settings.telegram_chat_id,
    )
    paper_service = PaperService(
        sources=sources,
        parser=parser,
        storage=storage,
        notifier=notifier,
        enable_translation=settings.enable_translation,
    )

    # Run pipeline
    stats = await run_once(paper_service)

    await storage.close()

    logger.info("Pipeline completed", **stats)
    return stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Citeo - arXiv RSS with AI")
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run pipeline once and exit (no API server)",
    )
    parser.add_argument(
        "--fetch-only",
        action="store_true",
        help="Only fetch and save papers (no AI processing or notifications)",
    )
    parser.add_argument(
        "--host",
        default=settings.api_host,
        help=f"API server host (default: {settings.api_host})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.api_port,
        help=f"API server port (default: {settings.api_port})",
    )
    args = parser.parse_args()

    # Configure logging
    configure_logging(
        log_level=settings.log_level,
        json_format=settings.log_json,
    )

    if args.run_once or args.fetch_only:
        # Run once and exit
        asyncio.run(run_cli_once())
    else:
        # Start API server with scheduler
        app = create_app()
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level=settings.log_level.lower(),
        )


if __name__ == "__main__":
    main()
