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

    def __init__(
        self,
        token: str,
        chat_id: str,
        rate_limit_delay: float = 0.5,
        url_generator=None,
    ):
        """Initialize Telegram notifier.

        Args:
            token: Telegram Bot token.
            chat_id: Target chat ID to send messages to.
            rate_limit_delay: Delay between messages to avoid rate limiting.
            url_generator: Optional SignedURLGenerator for creating analysis links.
        """
        self._bot = Bot(token=token)
        self._chat_id = chat_id
        self._rate_limit_delay = rate_limit_delay
        self._url_generator = url_generator

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
        # Reason: Display 1-10 programmer recommendation score
        if summary and summary.relevance_score >= 1:
            score_emoji = self._get_score_emoji(summary.relevance_score)
            parts.append(f"\n{score_emoji} 推荐度: {summary.relevance_score:.1f}/10")

        # Links (with deep analysis link if URL generator available)
        parts.append("")

        if self._url_generator:
            try:
                analysis_url = self._url_generator.generate_analysis_url(
                    arxiv_id=paper.arxiv_id, platform="telegram"
                )
                parts.append(
                    f"🔗 <a href='{self._escape_url(paper.abs_url)}'>Abstract</a> | "
                    f"<a href='{self._escape_url(paper.pdf_url)}'>PDF</a> | "
                    f"<a href='{self._escape_url(analysis_url)}'>深度分析</a>"
                )
            except Exception as e:
                # Fallback if URL generation fails
                logger.warning("Failed to generate analysis URL", error=str(e))
                parts.append(
                    f"🔗 <a href='{self._escape_url(paper.abs_url)}'>Abstract</a> | "
                    f"<a href='{self._escape_url(paper.pdf_url)}'>PDF</a>"
                )
        else:
            # Original format without analysis link
            parts.append(
                f"🔗 <a href='{self._escape_url(paper.abs_url)}'>Abstract</a> | "
                f"<a href='{self._escape_url(paper.pdf_url)}'>PDF</a>"
            )

        return "\n".join(parts)

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters for text content."""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _escape_url(self, url: str) -> str:
        """Escape URL for use in HTML attributes.

        Reason: URLs in HTML href attributes need & escaped as &amp;
        """
        return url.replace("&", "&amp;")

    def _get_score_emoji(self, score: float) -> str:
        """Get emoji based on programmer recommendation score (1-10).

        Reason: Visual indication of paper's value to programmers.
        """
        if score >= 9:
            return "🔥🔥"  # 9-10: Must-read for programmers
        elif score >= 8:
            return "🔥"  # 8: Highly recommended
        elif score >= 6:
            return "⭐"  # 6-7: Worth reading
        elif score >= 4:
            return "📊"  # 4-5: Moderate interest
        else:
            return "📄"  # 1-3: Low relevance

    async def send_deep_analysis(self, paper: Paper) -> bool:
        """Send PDF deep analysis notification for a paper.

        Args:
            paper: The paper with deep_analysis in summary.

        Returns:
            bool: True if notification was sent successfully.
        """
        log = logger.bind(arxiv_id=paper.arxiv_id, chat_id=self._chat_id)

        # Check if deep analysis exists
        if not paper.summary or not paper.summary.deep_analysis:
            log.warning("No deep analysis available for paper")
            return False

        message = self._format_deep_analysis_message(paper)

        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=message,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False,
            )
            log.info("Deep analysis notification sent")
            return True

        except TelegramError as e:
            log.error("Failed to send deep analysis notification", error=str(e))
            return False

    def _format_deep_analysis_message(self, paper: Paper) -> str:
        """Format deep analysis as Telegram message.

        Reason: Separate formatting for deep analysis to keep messages focused.
        """
        if not paper.summary or not paper.summary.deep_analysis:
            return ""

        parts = []

        # Header
        parts.append("🔬 <b>深度分析完成</b>\n")

        # Title
        title = paper.summary.title_zh if paper.summary.title_zh else paper.title
        parts.append(f"<b>{self._escape_html(title)}</b>")
        parts.append(f"<code>{paper.arxiv_id}</code>\n")

        # Deep analysis content
        analysis = paper.summary.deep_analysis

        # Truncate if too long (keep it under Telegram limit)
        if len(analysis) > 3000:
            analysis = analysis[:3000] + "\n\n[分析内容过长，已截断...]"

        # Convert Markdown formatting to HTML
        # Reason: Telegram HTML mode doesn't support Markdown, need to convert
        analysis_html = self._markdown_to_html(analysis)
        parts.append(analysis_html)

        # Links
        parts.append("")

        # Reason: Add web view link for viewing formatted analysis in browser
        from citeo.config.settings import settings

        view_url = f"{settings.api_base_url}/api/view/{paper.arxiv_id}"
        parts.append(
            f"🔗 <a href='{self._escape_url(paper.abs_url)}'>Abstract</a> | "
            f"<a href='{self._escape_url(paper.pdf_url)}'>PDF</a> | "
            f"<a href='{self._escape_url(view_url)}'>完整查看</a>"
        )

        message = "\n".join(parts)

        # Final length check
        if len(message) > MAX_MESSAGE_LENGTH:
            message = message[: MAX_MESSAGE_LENGTH - 20] + "\n\n[截断...]"

        return message

    def _markdown_to_html(self, text: str) -> str:
        """Convert simple Markdown formatting to HTML for Telegram.

        Reason: Telegram ParseMode.HTML doesn't support Markdown syntax.
        """
        lines = text.split("\n")
        html_lines = []

        for line in lines:
            # Convert ## headings to bold
            if line.startswith("## "):
                line = f"<b>{self._escape_html(line[3:])}</b>"
            # Convert ### subheadings to bold
            elif line.startswith("### "):
                line = f"<b>{self._escape_html(line[4:])}</b>"
            # Convert bullet points
            elif line.startswith("- "):
                line = f"• {self._escape_html(line[2:])}"
            else:
                # Escape HTML for regular lines
                line = self._escape_html(line)

            html_lines.append(line)

        return "\n".join(html_lines)
