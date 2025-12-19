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
    ):
        """Initialize Feishu notifier.

        Args:
            webhook_url: Feishu bot webhook URL.
            secret: Optional signing secret for verification.
            rate_limit_delay: Delay between messages to avoid rate limiting.
        """
        self._webhook_url = webhook_url
        self._secret = secret
        self._rate_limit_delay = rate_limit_delay

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

    async def send_papers(self, papers: list[Paper]) -> int:
        """Send notifications for multiple papers.

        Args:
            papers: List of papers to notify about.

        Returns:
            Number of successfully sent notifications.
        """
        import asyncio

        if not papers:
            return 0

        # Send header message
        await self.send_message(f"📚 **arXiv Daily Update**\n今日新论文: {len(papers)} 篇")

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
        score_text = ""
        if summary and summary.relevance_score > 0:
            score = summary.relevance_score
            if score >= 0.8:
                emoji = "🔥"
            elif score >= 0.6:
                emoji = "⭐"
            else:
                emoji = "📊"
            score_text = f"{emoji} 相关性: {score:.0%}"

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

        # Action buttons
        elements.append({"tag": "hr"})
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
                ],
            }
        )

        return {
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": title[:50]},
            },
            "elements": elements,
        }
