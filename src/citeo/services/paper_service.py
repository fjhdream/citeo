"""Paper processing service - main orchestration layer.

Coordinates RSS fetching, AI processing, storage, and notifications.
"""

import asyncio
from datetime import timedelta

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
        sources: list[ArxivFeedSource],
        parser: ArxivParser,
        storage: PaperStorage,
        notifier: TelegramNotifier,
        enable_translation: bool = True,
        max_concurrent_ai: int = 5,
        min_notification_score: float = 8.0,
        max_daily_notifications: int | None = 10,
    ):
        """Initialize paper service.

        Args:
            sources: List of RSS feed sources.
            parser: RSS parser instance.
            storage: Paper storage instance.
            notifier: Notification sender instance.
            enable_translation: Whether to enable AI translation.
            max_concurrent_ai: Maximum concurrent AI processing tasks.
            min_notification_score: Minimum score for notification (1-10).
            max_daily_notifications: Maximum number of papers to notify per day (None = unlimited).
        """
        self._sources = sources
        self._parser = parser
        self._storage = storage
        self._notifier = notifier
        self._enable_translation = enable_translation
        self._max_concurrent_ai = max_concurrent_ai
        self._min_notification_score = min_notification_score
        self._max_daily_notifications = max_daily_notifications

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

        all_papers: list[Paper] = []

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

    async def _fetch_and_parse(self, source: ArxivFeedSource) -> list[Paper]:
        """Fetch and parse a single feed source."""
        raw_content = await source.fetch_raw()
        return self._parser.parse(raw_content, source.source_id)

    async def _save_new_papers(self, papers: list[Paper]) -> list[Paper]:
        """Save papers, returning only new ones (deduplication)."""
        new_papers = []
        for paper in papers:
            is_new = await self._storage.save_paper(paper)
            if is_new:
                new_papers.append(paper)
        return new_papers

    async def _process_with_ai(self, papers: list[Paper]) -> list[Paper]:
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

    async def _notify(self, papers: list[Paper]) -> int:
        """Send notifications for papers with score >= threshold.

        Reason: Filter papers by recommendation score to only notify about
        highly relevant papers for programmers (score >= threshold). Sort by score
        in descending order to show most important papers first.
        """
        # Filter papers with score >= threshold (only those with AI summary)
        # Reason: Only recommend papers that are highly relevant to programmers
        high_score_papers = [
            p
            for p in papers
            if p.summary and p.summary.relevance_score >= self._min_notification_score
        ]

        # Sort by relevance score (descending)
        # Reason: Show most important papers first
        high_score_papers.sort(
            key=lambda p: p.summary.relevance_score if p.summary else 0, reverse=True
        )

        # Apply daily notification limit with intelligent selection
        # Reason: When there are many high-scoring papers, use AI agent to ensure
        # diversity and complementarity instead of simple score-based truncation
        total_high_score = len(high_score_papers)
        if self._max_daily_notifications and len(high_score_papers) > self._max_daily_notifications:
            # Use intelligent selection when AI is enabled
            # Reason: Only use AI selection if enable_translation=True, since it requires
            # the same OpenAI infrastructure. If AI is disabled, fall back to simple truncation.
            if self._enable_translation:
                try:
                    from citeo.ai.selector import select_papers

                    logger.info(
                        "Using intelligent selection for paper filtering",
                        total_papers=total_high_score,
                        target_count=self._max_daily_notifications,
                    )

                    high_score_papers = await select_papers(
                        high_score_papers,
                        max_count=self._max_daily_notifications,
                    )

                except Exception as e:
                    logger.warning(
                        "Intelligent selection failed, using simple truncation",
                        error=str(e),
                    )
                    # Fallback to simple truncation
                    high_score_papers = high_score_papers[: self._max_daily_notifications]
            else:
                # Simple truncation when AI is disabled
                high_score_papers = high_score_papers[: self._max_daily_notifications]

            logger.info(
                "Applied daily notification limit",
                total_high_score=total_high_score,
                limit=self._max_daily_notifications,
                sending=len(high_score_papers),
                truncated_count=total_high_score - len(high_score_papers),
            )

        log = logger.bind(
            total_papers=len(papers),
            high_score_papers=total_high_score,
            sending_papers=len(high_score_papers),
            min_score=self._min_notification_score,
            max_limit=self._max_daily_notifications,
        )
        log.info(
            "Filtering papers for notification",
            filtered_count=total_high_score,
            sending_count=len(high_score_papers),
        )

        if not high_score_papers:
            log.info(
                f"No papers with score >= {self._min_notification_score}, skipping notifications"
            )
            # Still mark all as notified even if not sent
            # Reason: Avoid reprocessing low-score papers in future runs
            for paper in papers:
                await self._storage.mark_as_notified(paper.guid)
            return 0

        success_count = await self._notifier.send_papers(
            high_score_papers, total_filtered_count=total_high_score
        )

        # Mark all papers as notified (both sent and filtered)
        # Reason: Avoid reprocessing low-score papers in future runs
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

        all_papers: list[Paper] = []
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

    async def trigger_daily_task(self, force: bool = False) -> dict:
        """Manually trigger today's daily task.

        Intelligently handles different scenarios:
        - If no papers fetched today: Run full pipeline
        - If papers exist but unnotified: Process and notify
        - If all notified and force=True: Reset and re-notify
        - If all notified and force=False: Return status only

        Args:
            force: If True, re-notify already notified papers.

        Returns:
            dict: Execution statistics with status.

        Reason: Centralized logic for manual daily task triggering,
        reusing existing pipeline components while adding smart detection.
        """
        from datetime import datetime

        log = logger.bind(job="trigger_daily_task", force=force)
        log.info("Manual daily task trigger requested")

        # Get today's date range (UTC)
        # Reason: All timestamps in database are UTC, so we use utcnow()
        now_utc = datetime.utcnow()
        start_today = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        end_today = start_today + timedelta(days=1)

        # Check papers fetched today
        today_papers = await self._storage.get_papers_by_fetched_date(start_today, end_today)

        stats = {
            "status": "",
            "papers_total": len(today_papers),
            "papers_fetched": 0,
            "papers_new": 0,
            "papers_processed": 0,
            "papers_notified": 0,
            "errors": [],
        }

        # Scenario 1: No papers fetched today - run full pipeline
        if not today_papers:
            log.info("No papers fetched today, running full pipeline")
            pipeline_stats = await self.run_daily_pipeline()
            stats.update(pipeline_stats)
            stats["status"] = "fetched_and_notified"
            return stats

        # Check notification status
        notified_papers = [p for p in today_papers if p.is_notified]
        unnotified_papers = [p for p in today_papers if not p.is_notified]

        log.info(
            "Today's papers status",
            total=len(today_papers),
            notified=len(notified_papers),
            unnotified=len(unnotified_papers),
        )

        # Scenario 2: Some papers not notified yet
        if unnotified_papers:
            log.info("Processing unnotified papers from today")

            # AI process papers without summary
            papers_to_process = [p for p in unnotified_papers if p.summary is None]
            if papers_to_process and self._enable_translation:
                processed = await self._process_with_ai(papers_to_process)
                stats["papers_processed"] = len(processed)

            # Reload papers to get updated summaries
            today_papers = await self._storage.get_papers_by_fetched_date(start_today, end_today)
            unnotified_papers = [p for p in today_papers if not p.is_notified]

            # Send notifications
            notified_count = await self._notify(unnotified_papers)
            stats["papers_notified"] = notified_count
            stats["status"] = "processed_and_notified"

            log.info("Unnotified papers processed", notified=notified_count)
            return stats

        # Scenario 3: All papers already notified
        if force:
            log.info("Force re-notification of today's papers")

            # Reset notification status
            guids = [p.guid for p in today_papers]
            await self._storage.reset_notification_status(guids)

            # Reload papers with reset status
            today_papers = await self._storage.get_papers_by_fetched_date(start_today, end_today)

            # Re-send notifications
            notified_count = await self._notify(today_papers)
            stats["papers_notified"] = notified_count
            stats["status"] = "re_notified"

            log.info("Papers re-notified", count=notified_count)
            return stats
        else:
            log.info("All papers already notified, use force=true to re-send")
            stats["status"] = "already_notified"
            stats["papers_notified"] = 0
            return stats
