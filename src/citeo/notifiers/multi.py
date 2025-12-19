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

    async def send_papers(self, papers: list[Paper]) -> int:
        """Send notifications for multiple papers to all channels.

        Args:
            papers: List of papers to notify about.

        Returns:
            Number of papers successfully sent to at least one channel.
        """
        if not self._notifiers or not papers:
            return 0

        # Send to all notifiers in parallel
        results = await asyncio.gather(
            *[n.send_papers(papers) for n in self._notifiers],
            return_exceptions=True,
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
