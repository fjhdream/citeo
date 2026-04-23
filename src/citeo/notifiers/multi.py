"""Multi-notifier that sends to multiple channels simultaneously."""

import asyncio

import structlog

from citeo.models.paper import Paper
from citeo.notifiers.base import Notifier

logger = structlog.get_logger()


class MultiNotifier:
    """Notifier that sends to multiple channels.

    Reason: Allows simultaneous notification to Telegram, Feishu, and
    other channels without changing the service layer code.
    """

    def __init__(self, notifiers: list[Notifier]):
        """Initialize multi-notifier.

        Args:
            notifiers: List of notifier instances to send to.
        """
        self._notifiers = notifiers

    async def send_paper(self, paper: Paper) -> bool:
        """Send notification for a single paper to all channels.

        Args:
            paper: The paper to notify about.

        Returns:
            True if at least one channel succeeded.
        """
        if not self._notifiers:
            return False

        results = await asyncio.gather(
            *[n.send_paper(paper) for n in self._notifiers],
            return_exceptions=True,
        )

        success = any(r is True for r in results)
        failures = [r for r in results if isinstance(r, Exception)]

        if failures:
            for e in failures:
                logger.warning("Notifier failed", error=str(e))

        return success

    async def send_papers(
        self, papers: list[Paper], total_filtered_count: int | None = None
    ) -> int:
        """Send notifications for multiple papers to all channels.

        Args:
            papers: List of papers to notify about.
            total_filtered_count: Total number of high-score papers before truncation (for display).

        Returns:
            Number of papers successfully sent to at least one channel.
        """
        if not self._notifiers or not papers:
            return 0

        logger.info(
            "MultiNotifier sending papers to all channels",
            notifier_count=len(self._notifiers),
            paper_count=len(papers),
        )

        # Group notifiers by type to handle rate limiting
        # Reason: Multiple Telegram bots sending to same chat_id need sequential execution
        # to avoid Telegram API rate limits, but different platforms can run in parallel
        from citeo.notifiers.telegram import TelegramNotifier

        telegram_notifiers = [n for n in self._notifiers if isinstance(n, TelegramNotifier)]
        other_notifiers = [n for n in self._notifiers if not isinstance(n, TelegramNotifier)]

        results = []

        # Send to Telegram bots sequentially to avoid rate limiting
        if telegram_notifiers:
            logger.info(
                "Sending to Telegram bots sequentially",
                telegram_count=len(telegram_notifiers),
            )
            for i, notifier in enumerate(telegram_notifiers):
                try:
                    result = await notifier.send_papers(papers, total_filtered_count=total_filtered_count)
                    results.append(result)
                    logger.info(
                        "Telegram notifier sent papers successfully",
                        notifier_index=i,
                        success_count=result,
                    )
                except Exception as e:
                    results.append(e)
                    logger.error(
                        "Telegram notifier failed to send papers",
                        notifier_index=i,
                        error=str(e),
                    )

        # Send to other platforms in parallel (they don't share rate limits)
        if other_notifiers:
            logger.info(
                "Sending to other platforms in parallel",
                other_count=len(other_notifiers),
            )
            other_results = await asyncio.gather(
                *[
                    n.send_papers(papers, total_filtered_count=total_filtered_count)
                    for n in other_notifiers
                ],
                return_exceptions=True,
            )
            results.extend(other_results)

            # Log results for other notifiers
            for i, (notifier, result) in enumerate(zip(other_notifiers, other_results)):
                notifier_type = type(notifier).__name__
                if isinstance(result, Exception):
                    logger.error(
                        "Notifier failed to send papers",
                        notifier_index=len(telegram_notifiers) + i,
                        notifier_type=notifier_type,
                        error=str(result),
                    )
                elif isinstance(result, int):
                    logger.info(
                        "Notifier sent papers successfully",
                        notifier_index=len(telegram_notifiers) + i,
                        notifier_type=notifier_type,
                        success_count=result,
                    )

        # Return the max success count across all notifiers
        success_counts = [r for r in results if isinstance(r, int)]
        return max(success_counts) if success_counts else 0

    async def send_message(self, message: str) -> bool:
        """Send a plain text message to all channels.

        Args:
            message: The message to send.

        Returns:
            True if at least one channel succeeded.
        """
        if not self._notifiers:
            return False

        results = await asyncio.gather(
            *[n.send_message(message) for n in self._notifiers],
            return_exceptions=True,
        )

        return any(r is True for r in results)

    async def send_deep_analysis(self, paper: Paper) -> bool:
        """Send PDF deep analysis notification to all channels.

        Args:
            paper: The paper with deep_analysis in summary.

        Returns:
            True if at least one channel succeeded.
        """
        if not self._notifiers:
            return False

        results = await asyncio.gather(
            *[n.send_deep_analysis(paper) for n in self._notifiers],
            return_exceptions=True,
        )

        success = any(r is True for r in results)
        failures = [r for r in results if isinstance(r, Exception)]

        if failures:
            for e in failures:
                logger.warning("Notifier failed to send deep analysis", error=str(e))

        return success
