"""Telegram notification implementation.

Sends paper notifications via Telegram Bot API.
"""

import asyncio

import structlog
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

from citeo.models.paper import Paper

logger = structlog.get_logger()

# Telegram message length limit
MAX_MESSAGE_LENGTH = 4096


class TelegramNotifier:
    """Telegram Bot notification implementation.

    Sends paper notifications to a specified Telegram chat.
    Each paper is sent as an individual message (逐篇推送).
    """

    def __init__(self, token: str, chat_id: str, rate_limit_delay: float = 0.5):
        """Initialize Telegram notifier.

        Args:
            token: Telegram Bot token.
            chat_id: Target chat ID to send messages to.
            rate_limit_delay: Delay between messages to avoid rate limiting.
        """
        self._bot = Bot(token=token)
        self._chat_id = chat_id
        self._rate_limit_delay = rate_limit_delay

    async def send_paper(self, paper: Paper) -> bool:
        """Send notification for a single paper.

        Formats the paper with AI summary (if available) and sends to Telegram.

        Args:
            paper: The paper to notify about.

        Returns:
            bool: True if notification was sent successfully.
        """
        log = logger.bind(arxiv_id=paper.arxiv_id, chat_id=self._chat_id)

        message = self._format_paper_message(paper)

        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False,
            )
            log.info("Paper notification sent")
            return True

        except TelegramError as e:
            log.error("Failed to send paper notification", error=str(e))
            return False

    async def send_papers(self, papers: list[Paper]) -> int:
        """Send notifications for multiple papers.

        Args:
            papers: List of papers to notify about.

        Returns:
            Number of successfully sent notifications.
        """
        if not papers:
            return 0

        # Send header message
        header = f"📚 <b>arXiv Daily Update</b>\n今日新论文: {len(papers)} 篇\n"
        await self.send_message(header)

        success_count = 0
        for paper in papers:
            if await self.send_paper(paper):
                success_count += 1

            # Rate limiting delay
            await asyncio.sleep(self._rate_limit_delay)

        return success_count

    async def send_message(self, message: str) -> bool:
        """Send a plain text message.

        Args:
            message: The message to send (supports HTML formatting).

        Returns:
            bool: True if message was sent successfully.
        """
        log = logger.bind(chat_id=self._chat_id)

        # Truncate if too long
        if len(message) > MAX_MESSAGE_LENGTH:
            message = message[: MAX_MESSAGE_LENGTH - 20] + "\n\n[截断...]"

        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode=ParseMode.HTML,
            )
            log.debug("Message sent")
            return True

        except TelegramError as e:
            log.error("Failed to send message", error=str(e))
            return False

    def _format_paper_message(self, paper: Paper) -> str:
        """Format paper as Telegram message.

        Reason: Using HTML format for better readability in Telegram.
        """
        summary = paper.summary
        parts = []

        # Title (Chinese if available, otherwise original)
        if summary and summary.title_zh:
            parts.append(f"<b>{self._escape_html(summary.title_zh)}</b>")
            parts.append(f"<i>{self._escape_html(paper.title)}</i>")
        else:
            parts.append(f"<b>{self._escape_html(paper.title)}</b>")

        # Authors (truncate if too many)
        if paper.authors:
            authors_str = ", ".join(paper.authors[:3])
            if len(paper.authors) > 3:
                authors_str += f" et al. ({len(paper.authors)} authors)"
            parts.append(f"👤 {self._escape_html(authors_str)}")

        # Categories as hashtags
        if paper.categories:
            tags = " ".join(f"#{cat.replace('.', '_')}" for cat in paper.categories[:3])
            parts.append(tags)

        parts.append("")  # Empty line

        # Abstract (Chinese if available)
        if summary and summary.abstract_zh:
            abstract_text = summary.abstract_zh
        else:
            abstract_text = paper.abstract

        # Truncate abstract if too long
        if len(abstract_text) > 800:
            abstract_text = abstract_text[:800] + "..."

        parts.append(self._escape_html(abstract_text))

        # Key points (if available)
        if summary and summary.key_points:
            parts.append("")
            parts.append("<b>📌 要点:</b>")
            for point in summary.key_points[:4]:
                parts.append(f"• {self._escape_html(point)}")

        # Relevance score (if available)
        if summary and summary.relevance_score > 0:
            score_emoji = self._get_score_emoji(summary.relevance_score)
            parts.append(f"\n{score_emoji} 相关性: {summary.relevance_score:.1%}")

        # Links
        parts.append("")
        parts.append(
            f"🔗 <a href='{paper.abs_url}'>Abstract</a> | "
            f"<a href='{paper.pdf_url}'>PDF</a>"
        )

        return "\n".join(parts)

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def _get_score_emoji(self, score: float) -> str:
        """Get emoji based on relevance score."""
        if score >= 0.8:
            return "🔥"
        elif score >= 0.6:
            return "⭐"
        elif score >= 0.4:
            return "📊"
        else:
            return "📄"
