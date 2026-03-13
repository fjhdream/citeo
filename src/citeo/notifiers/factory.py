"""Notifier factory for creating notifiers based on configuration."""

import structlog

from citeo.notifiers.base import Notifier
from citeo.notifiers.feishu import FeishuNotifier
from citeo.notifiers.multi import MultiNotifier
from citeo.notifiers.telegram import TelegramNotifier

logger = structlog.get_logger()


def create_notifiers_from_channels(
    channels: list[dict],
    url_generator=None,
) -> Notifier | MultiNotifier:
    """Create notifier(s) from a list of channel config dicts.

    Each dict must have a "type" key ("telegram" or "feishu") plus
    type-specific fields. Supports multiple instances of the same type.

    Args:
        channels: List of channel config dicts.
        url_generator: Optional SignedURLGenerator for creating analysis links.

    Returns:
        Single notifier or MultiNotifier if multiple channels configured.

    Raises:
        ValueError: If required config is missing or no valid channels.
    """
    notifiers: list[Notifier] = []

    for ch in channels:
        ntype = ch.get("type", "").strip().lower()

        if ntype == "telegram":
            token = ch.get("token")
            chat_id = ch.get("chat_id")
            if not token or not chat_id:
                raise ValueError("Telegram channel requires 'token' and 'chat_id'")
            notifiers.append(
                TelegramNotifier(token=token, chat_id=chat_id, url_generator=url_generator)
            )
            logger.info("Telegram notifier configured (channels)", chat_id=chat_id)

        elif ntype == "feishu":
            webhook_url = ch.get("webhook_url")
            if not webhook_url:
                raise ValueError("Feishu channel requires 'webhook_url'")
            notifiers.append(
                FeishuNotifier(
                    webhook_url=webhook_url,
                    secret=ch.get("secret"),
                    url_generator=url_generator,
                )
            )
            logger.info("Feishu notifier configured (channels)")

        else:
            logger.warning("Unknown notifier type in channels", type=ntype)

    if not notifiers:
        raise ValueError("No valid notifiers configured in NOTIFIER_CHANNELS")

    if len(notifiers) == 1:
        return notifiers[0]

    logger.info("Multi-notifier configured (channels)", count=len(notifiers))
    return MultiNotifier(notifiers)


def create_notifier(
    notifier_types: list[str],
    telegram_token: str | None = None,
    telegram_chat_id: str | None = None,
    feishu_webhook_url: str | None = None,
    feishu_secret: str | None = None,
    url_generator=None,
) -> Notifier | MultiNotifier:
    """Create notifier(s) based on configuration.

    Args:
        notifier_types: List of notifier types to create ("telegram", "feishu").
        telegram_token: Telegram bot token.
        telegram_chat_id: Telegram chat ID.
        feishu_webhook_url: Feishu webhook URL.
        feishu_secret: Feishu signing secret.
        url_generator: Optional SignedURLGenerator for creating analysis links.

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
                TelegramNotifier(
                    token=telegram_token,
                    chat_id=telegram_chat_id,
                    url_generator=url_generator,
                )
            )
            logger.info(
                "Telegram notifier configured",
                chat_id=telegram_chat_id,
                has_url_generator=url_generator is not None,
            )

        elif ntype == "feishu":
            if not feishu_webhook_url:
                raise ValueError("Feishu notifier requires FEISHU_WEBHOOK_URL")
            notifiers.append(
                FeishuNotifier(
                    webhook_url=feishu_webhook_url,
                    secret=feishu_secret,
                    url_generator=url_generator,
                )
            )
            logger.info(
                "Feishu notifier configured",
                has_url_generator=url_generator is not None,
            )

        else:
            logger.warning("Unknown notifier type", type=ntype)

    if not notifiers:
        raise ValueError("No valid notifiers configured")

    if len(notifiers) == 1:
        return notifiers[0]

    logger.info("Multi-notifier configured", count=len(notifiers))
    return MultiNotifier(notifiers)
