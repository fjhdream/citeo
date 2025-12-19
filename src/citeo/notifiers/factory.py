"""Notifier factory for creating notifiers based on configuration."""

import structlog

from citeo.notifiers.base import Notifier
from citeo.notifiers.feishu import FeishuNotifier
from citeo.notifiers.multi import MultiNotifier
from citeo.notifiers.telegram import TelegramNotifier

logger = structlog.get_logger()


def create_notifier(
    notifier_types: list[str],
    telegram_token: str | None = None,
    telegram_chat_id: str | None = None,
    feishu_webhook_url: str | None = None,
    feishu_secret: str | None = None,
) -> Notifier | MultiNotifier:
    """Create notifier(s) based on configuration.

    Args:
        notifier_types: List of notifier types to create ("telegram", "feishu").
        telegram_token: Telegram bot token.
        telegram_chat_id: Telegram chat ID.
        feishu_webhook_url: Feishu webhook URL.
        feishu_secret: Feishu signing secret.

    Returns:
        Single notifier or MultiNotifier if multiple types configured.

    Raises:
        ValueError: If required config is missing for a notifier type.
    """
    notifiers: list[Notifier] = []

    for ntype in notifier_types:
        ntype = ntype.strip().lower()

        if ntype == "telegram":
            if not telegram_token or not telegram_chat_id:
                raise ValueError(
                    "Telegram notifier requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
                )
            notifiers.append(
                TelegramNotifier(token=telegram_token, chat_id=telegram_chat_id)
            )
            logger.info("Telegram notifier configured", chat_id=telegram_chat_id)

        elif ntype == "feishu":
            if not feishu_webhook_url:
                raise ValueError("Feishu notifier requires FEISHU_WEBHOOK_URL")
            notifiers.append(
                FeishuNotifier(webhook_url=feishu_webhook_url, secret=feishu_secret)
            )
            logger.info("Feishu notifier configured")

        else:
            logger.warning("Unknown notifier type", type=ntype)

    if not notifiers:
        raise ValueError("No valid notifiers configured")

    if len(notifiers) == 1:
        return notifiers[0]

    logger.info("Multi-notifier configured", count=len(notifiers))
    return MultiNotifier(notifiers)
