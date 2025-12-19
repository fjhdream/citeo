"""Abstract notifier interface using Protocol."""

from typing import Protocol

from citeo.models.paper import Paper


class Notifier(Protocol):
    """Notification channel abstraction protocol.

    Defines the contract for sending paper notifications to various channels.
    """

    async def send_paper(self, paper: Paper) -> bool:
        """Send notification for a single paper.

        Args:
            paper: The paper to send notification for.

        Returns:
            bool: True if notification was sent successfully.
        """
        ...

    async def send_message(self, message: str) -> bool:
        """Send a plain text message.

        Args:
            message: The message to send.

        Returns:
            bool: True if message was sent successfully.
        """
        ...
