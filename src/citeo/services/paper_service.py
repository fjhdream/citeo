"""Paper processing service - main orchestration layer.

Coordinates RSS fetching, AI processing, storage, and notifications.
"""

import asyncio
from typing import List

import structlog

from citeo.ai.summarizer import summarize_paper
from citeo.exceptions import AIProcessingError, FetchError
from citeo.models.paper import Paper
from citeo.notifiers.telegram import TelegramNotifier
from citeo.parsers.arxiv_parser import ArxivParser
from citeo.sources.arxiv import ArxivFeedSource
from citeo.storage.base import PaperStorage

logger = structlog.get_logger()


class PaperService:
    """Paper processing service.

    Reason: Acts as Facade pattern, orchestrating all modules
    to complete the full business workflow.
    """

    def __init__(
        self,
        sources: List[ArxivFeedSource],
        parser: ArxivParser,
        storage: PaperStorage,
        notifier: TelegramNotifier,
        enable_translation: bool = True,
        max_concurrent_ai: int = 5,
    ):
        """Initialize paper service.

        Args:
            sources: List of RSS feed sources.
            parser: RSS parser instance.
            storage: Paper storage instance.
            notifier: Notification sender instance.
            enable_translation: Whether to enable AI translation.
            max_concurrent_ai: Maximum concurrent AI processing tasks.
        """
        self._sources = sources
        self._parser = parser
        self._storage = storage
        self._notifier = notifier
        self._enable_translation = enable_translation
        self._max_concurrent_ai = max_concurrent_ai

    async def run_daily_pipeline(self) -> dict:
        """Execute the daily processing pipeline.

        Full workflow:
        1. Fetch RSS from all sources
        2. Parse and deduplicate papers
        3. AI summarize/translate new papers
        4. Send notifications

        Returns:
            dict: Pipeline execution statistics.
        """
        log = logger.bind(job="daily_pipeline")
        log.info("Starting daily pipeline")

        stats = {
            "papers_fetched": 0,
            "papers_new": 0,
            "papers_processed": 0,
            "papers_notified": 0,
            "errors": [],
        }

        all_papers: List[Paper] = []

        # Step 1: Fetch and parse from all sources
        for source in self._sources:
            try:
                papers = await self._fetch_and_parse(source)
                all_papers.extend(papers)
                stats["papers_fetched"] += len(papers)
                log.info(
                    "Source fetched",
                    source_id=source.source_id,
                    paper_count=len(papers),
                )
            except FetchError as e:
                log.warning("Feed fetch failed", source=source.source_id, error=str(e))
                stats["errors"].append(f"Fetch failed: {source.source_id}")

        # Step 2: Deduplicate and save
        new_papers = await self._save_new_papers(all_papers)
        stats["papers_new"] = len(new_papers)
        log.info("New papers saved", count=len(new_papers))

        if not new_papers:
            log.info("No new papers to process")
            return stats

        # Step 3: AI processing
        if self._enable_translation:
            processed_papers = await self._process_with_ai(new_papers)
        else:
            processed_papers = new_papers
        stats["papers_processed"] = len(processed_papers)

        # Step 4: Send notifications
        notified_count = await self._notify(processed_papers)
        stats["papers_notified"] = notified_count

        log.info(
            "Daily pipeline completed",
            fetched=stats["papers_fetched"],
            new=stats["papers_new"],
            processed=stats["papers_processed"],
            notified=stats["papers_notified"],
        )

        return stats

    async def _fetch_and_parse(self, source: ArxivFeedSource) -> List[Paper]:
        """Fetch and parse a single feed source."""
        raw_content = await source.fetch_raw()
        return self._parser.parse(raw_content, source.source_id)

    async def _save_new_papers(self, papers: List[Paper]) -> List[Paper]:
        """Save papers, returning only new ones (deduplication)."""
        new_papers = []
        for paper in papers:
            is_new = await self._storage.save_paper(paper)
            if is_new:
                new_papers.append(paper)
        return new_papers

    async def _process_with_ai(self, papers: List[Paper]) -> List[Paper]:
        """Process papers with AI summarization/translation.

        Reason: Use asyncio.gather with Semaphore for parallel processing to speed up
        AI calls while preventing rate limits. Papers with failed AI processing are still
        included without summary.
        """
        # Create semaphore to limit concurrent AI requests
        # Reason: Prevents overwhelming OpenAI API with too many parallel requests
        semaphore = asyncio.Semaphore(self._max_concurrent_ai)

        async def process_single(paper: Paper) -> Paper:
            """Process a single paper with AI, respecting concurrency limit."""
            async with semaphore:
                try:
                    summary = await summarize_paper(paper)
                    paper.summary = summary
                    # Update summary in database
                    await self._storage.update_summary(paper.guid, summary)
                except AIProcessingError as e:
                    logger.warning(
                        "AI processing failed, using original",
                        paper=paper.arxiv_id,
                        error=str(e),
                    )
                    # Paper will be returned without summary
                return paper

        # Process all papers in parallel (with concurrency limit)
        # Reason: AI API calls are I/O bound, parallel execution significantly reduces total time
        processed = await asyncio.gather(
            *[process_single(paper) for paper in papers],
            return_exceptions=False,  # Already handling exceptions inside process_single
        )

        return list(processed)

    async def _notify(self, papers: List[Paper]) -> int:
        """Send notifications for papers."""
        success_count = await self._notifier.send_papers(papers)

        # Mark successful ones as notified
        for paper in papers:
            await self._storage.mark_as_notified(paper.guid)

        return success_count

    async def fetch_only(self) -> dict:
        """Fetch and save papers without AI processing or notifications.

        Useful for testing or manual runs.

        Returns:
            dict: Fetch statistics.
        """
        log = logger.bind(job="fetch_only")
        log.info("Starting fetch-only run")

        stats = {"papers_fetched": 0, "papers_new": 0}

        all_papers: List[Paper] = []
        for source in self._sources:
            try:
                papers = await self._fetch_and_parse(source)
                all_papers.extend(papers)
                stats["papers_fetched"] += len(papers)
            except FetchError as e:
                log.warning("Fetch failed", source=source.source_id, error=str(e))

        new_papers = await self._save_new_papers(all_papers)
        stats["papers_new"] = len(new_papers)

        log.info("Fetch-only completed", **stats)
        return stats

    async def process_pending(self) -> dict:
        """Process pending papers that haven't been notified.

        Useful for retrying failed notifications.

        Returns:
            dict: Processing statistics.
        """
        log = logger.bind(job="process_pending")
        log.info("Processing pending papers")

        pending = await self._storage.get_pending_papers()
        log.info("Pending papers found", count=len(pending))

        if not pending:
            return {"papers_pending": 0, "papers_notified": 0}

        # Process papers without summary
        papers_to_process = [p for p in pending if p.summary is None]
        if papers_to_process and self._enable_translation:
            await self._process_with_ai(papers_to_process)

        # Reload from storage to get updated summaries
        pending = await self._storage.get_pending_papers()

        notified = await self._notify(pending)

        return {"papers_pending": len(pending), "papers_notified": notified}
