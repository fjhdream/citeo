"""Feishu (Lark) notification implementation.

Sends paper notifications via Feishu Bot Webhook.
"""

import base64
import hashlib
import hmac
import time
from typing import Any

import httpx
import structlog

from citeo.models.paper import Paper

logger = structlog.get_logger()


class FeishuNotifier:
    """Feishu Bot webhook notification implementation.

    Sends paper notifications to Feishu group via webhook.
    Supports optional signature verification.
    """

    def __init__(
        self,
        webhook_url: str,
        secret: str | None = None,
        rate_limit_delay: float = 0.5,
        url_generator=None,
    ):
        """Initialize Feishu notifier.

        Args:
            webhook_url: Feishu bot webhook URL.
            secret: Optional signing secret for verification.
            rate_limit_delay: Delay between messages to avoid rate limiting.
            url_generator: Optional SignedURLGenerator for creating analysis links.
        """
        self._webhook_url = webhook_url
        self._secret = secret
        self._rate_limit_delay = rate_limit_delay
        self._url_generator = url_generator

    def _generate_sign(self, timestamp: int) -> str:
        """Generate signature for webhook verification.

        Args:
            timestamp: Unix timestamp in seconds.

        Returns:
            Base64 encoded HMAC-SHA256 signature.
        """
        if not self._secret:
            return ""

        string_to_sign = f"{timestamp}\n{self._secret}"
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        return base64.b64encode(hmac_code).decode("utf-8")

    async def _send_request(self, payload: dict[str, Any]) -> bool:
        """Send request to Feishu webhook.

        Args:
            payload: Message payload.

        Returns:
            True if successful.
        """
        # Add signature if secret is configured
        if self._secret:
            timestamp = int(time.time())
            payload["timestamp"] = str(timestamp)
            payload["sign"] = self._generate_sign(timestamp)

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    self._webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()

                result = response.json()
                if result.get("code") == 0:
                    return True
                else:
                    logger.error(
                        "Feishu API error",
                        code=result.get("code"),
                        msg=result.get("msg"),
                    )
                    return False

        except httpx.HTTPError as e:
            logger.error("Feishu request failed", error=str(e))
            return False

    async def send_paper(self, paper: Paper) -> bool:
        """Send notification for a single paper.

        Uses Feishu interactive card for rich formatting.

        Args:
            paper: The paper to notify about.

        Returns:
            True if notification was sent successfully.
        """
        log = logger.bind(arxiv_id=paper.arxiv_id)

        card = self._build_paper_card(paper)
        payload = {"msg_type": "interactive", "card": card}

        success = await self._send_request(payload)
        if success:
            log.info("Feishu paper notification sent")
        return success

    async def send_papers(
        self, papers: list[Paper], total_filtered_count: int | None = None
    ) -> int:
        """Send notifications for multiple papers.

        Args:
            papers: List of papers to notify about.
            total_filtered_count: Total number of high-score papers before truncation (for display).

        Returns:
            Number of successfully sent notifications.
        """
        import asyncio

        if not papers:
            return 0

        # Send header message with truncation info
        # Reason: Show users how many papers were selected vs total high-score papers
        if total_filtered_count and total_filtered_count > len(papers):
            # Show truncation: "10/25 篇"
            header_msg = (
                f"📚 **arXiv Daily Update**\n"
                f"今日新论文: {len(papers)}/{total_filtered_count} �� "
                f"(已按评分筛选)"
            )
        else:
            # No truncation: "10 篇"
            header_msg = f"📚 **arXiv Daily Update**\n今日新论文: {len(papers)} 篇"

        await self.send_message(header_msg)

        success_count = 0
        for paper in papers:
            if await self.send_paper(paper):
                success_count += 1
            await asyncio.sleep(self._rate_limit_delay)

        return success_count

    async def send_message(self, message: str) -> bool:
        """Send a plain text message.

        Args:
            message: The message to send (supports Markdown).

        Returns:
            True if message was sent successfully.
        """
        payload = {
            "msg_type": "text",
            "content": {"text": message},
        }
        return await self._send_request(payload)

    def _build_paper_card(self, paper: Paper) -> dict[str, Any]:
        """Build Feishu interactive card for a paper.

        Reason: Interactive cards provide rich formatting and better UX.
        """
        summary = paper.summary

        # Title
        if summary and summary.title_zh:
            title = summary.title_zh
            subtitle = paper.title
        else:
            title = paper.title
            subtitle = ""

        # Abstract
        if summary and summary.abstract_zh:
            abstract = summary.abstract_zh
        else:
            abstract = paper.abstract
        if len(abstract) > 500:
            abstract = abstract[:500] + "..."

        # Key points
        key_points_text = ""
        if summary and summary.key_points:
            key_points_text = "\n".join(f"• {p}" for p in summary.key_points[:4])

        # Score emoji
        # Reason: Display 1-10 programmer recommendation score
        score_text = ""
        if summary and summary.relevance_score >= 1:
            score = summary.relevance_score
            if score >= 9:
                emoji = "🔥🔥"
            elif score >= 8:
                emoji = "🔥"
            elif score >= 6:
                emoji = "⭐"
            else:
                emoji = "📊"
            score_text = f"{emoji} 推荐度: {score:.1f}/10"

        # Categories
        categories = " ".join(f"`{cat}`" for cat in paper.categories[:3])

        # Authors
        authors = ", ".join(paper.authors[:3])
        if len(paper.authors) > 3:
            authors += f" 等 ({len(paper.authors)}人)"

        # Build card elements
        elements: list[dict[str, Any]] = []

        # Subtitle (original title if translated)
        if subtitle:
            elements.append(
                {
                    "tag": "markdown",
                    "content": f"*{subtitle}*",
                }
            )

        # Authors and categories
        elements.append(
            {
                "tag": "markdown",
                "content": f"👤 {authors}\n{categories}",
            }
        )

        elements.append({"tag": "hr"})

        # Abstract
        elements.append(
            {
                "tag": "markdown",
                "content": abstract,
            }
        )

        # Key points
        if key_points_text:
            elements.append({"tag": "hr"})
            elements.append(
                {
                    "tag": "markdown",
                    "content": f"**📌 要点:**\n{key_points_text}",
                }
            )

        # Score
        if score_text:
            elements.append(
                {
                    "tag": "markdown",
                    "content": score_text,
                }
            )

        # Action buttons (with deep analysis button if URL generator available)
        actions = [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "📄 Abstract"},
                "type": "primary",
                "url": paper.abs_url,
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "📥 PDF"},
                "type": "default",
                "url": paper.pdf_url,
            },
        ]

        # Add deep analysis button if URL generator available
        if self._url_generator:
            try:
                analysis_url = self._url_generator.generate_analysis_url(
                    arxiv_id=paper.arxiv_id, platform="feishu"
                )
                actions.append(
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🔬 深度分析"},
                        "type": "danger",  # Red button for emphasis
                        "url": analysis_url,
                    }
                )
            except Exception as e:
                logger.warning("Failed to generate analysis URL", error=str(e))

        elements.append({"tag": "hr"})
        elements.append({"tag": "action", "actions": actions})

        return {
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": title[:50]},
            },
            "elements": elements,
        }

    async def send_deep_analysis(self, paper: Paper) -> bool:
        """Send PDF deep analysis notification for a paper.

        Uses Feishu interactive card for rich formatting.

        Args:
            paper: The paper with deep_analysis in summary.

        Returns:
            True if notification was sent successfully.
        """
        log = logger.bind(arxiv_id=paper.arxiv_id)

        # Check if deep analysis exists
        if not paper.summary or not paper.summary.deep_analysis:
            log.warning("No deep analysis available for paper")
            return False

        card = self._build_deep_analysis_card(paper)
        payload = {"msg_type": "interactive", "card": card}

        success = await self._send_request(payload)
        if success:
            log.info("Feishu deep analysis notification sent")
        return success

    def _build_deep_analysis_card(self, paper: Paper) -> dict[str, Any]:
        """Build Feishu interactive card for deep analysis.

        Reason: Use interactive cards for consistent rich formatting.
        """
        if not paper.summary or not paper.summary.deep_analysis:
            return {}

        summary = paper.summary

        # Title
        title = summary.title_zh if summary.title_zh else paper.title

        # Deep analysis content
        analysis = summary.deep_analysis

        # Truncate if too long
        if len(analysis) > 2500:
            analysis = analysis[:2500] + "\n\n[分析内容过长，已截断...]"

        # Build card elements
        elements: list[dict[str, Any]] = []

        # Header note
        elements.append(
            {
                "tag": "markdown",
                "content": f"**{paper.arxiv_id}**",
            }
        )

        elements.append({"tag": "hr"})

        # Deep analysis content
        elements.append(
            {
                "tag": "markdown",
                "content": analysis,
            }
        )

        # Action buttons
        elements.append({"tag": "hr"})

        # Reason: Add web view button for viewing formatted analysis in browser
        from citeo.config.settings import settings

        view_url = f"{settings.api_base_url}/api/view/{paper.arxiv_id}"

        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📄 Abstract"},
                        "type": "primary",
                        "url": paper.abs_url,
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📥 PDF"},
                        "type": "default",
                        "url": paper.pdf_url,
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🌐 完整查看"},
                        "type": "default",
                        "url": view_url,
                    },
                ],
            }
        )

        return {
            "header": {
                "template": "green",
                "title": {"tag": "plain_text", "content": f"🔬 深度分析: {title[:40]}"},
            },
            "elements": elements,
        }
