"""Abstract storage interface using Protocol.

Defines the contract for paper storage implementations.
"""

from datetime import datetime
from typing import Protocol

from citeo.models.paper import Paper, PaperSummary


class PaperStorage(Protocol):
    """Paper storage abstraction protocol.

    Reason: Using Protocol instead of ABC allows more flexible implementations
    while maintaining strict type checking.
    """

    async def initialize(self) -> None:
        """Initialize the storage (create tables, etc.)."""
        ...

    async def save_paper(self, paper: Paper) -> bool:
        """Save a paper to storage.

        Args:
            paper: The paper to save.

        Returns:
            bool: True if paper was saved (new), False if already exists (dedup).
        """
        ...

    async def get_paper_by_guid(self, guid: str) -> Paper | None:
        """Get a paper by its GUID.

        Args:
            guid: The paper's unique identifier.

        Returns:
            The paper if found, None otherwise.
        """
        ...

    async def get_paper_by_arxiv_id(self, arxiv_id: str) -> Paper | None:
        """Get a paper by its arXiv ID.

        Args:
            arxiv_id: The arXiv identifier (e.g., "2512.14709").

        Returns:
            The paper if found, None otherwise.
        """
        ...

    async def get_papers_by_date(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[Paper]:
        """Get papers within a date range.

        Args:
            start_date: Start of the date range.
            end_date: End of the date range.

        Returns:
            List of papers published within the range.
        """
        ...

    async def count_papers_by_date(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> int:
        """Count papers within a date range.

        Args:
            start_date: Start of the date range.
            end_date: End of the date range.

        Returns:
            Number of papers published within the range.

        Reason: Enables efficient pagination by getting total count
        without loading all paper objects.
        """
        ...

    async def get_pending_papers(self) -> list[Paper]:
        """Get papers that haven't been notified yet.

        Returns:
            List of papers waiting to be sent.
        """
        ...

    async def mark_as_notified(self, guid: str) -> None:
        """Mark a paper as notified.

        Args:
            guid: The paper's GUID to mark.
        """
        ...

    async def update_summary(self, guid: str, summary: PaperSummary) -> None:
        """Update a paper's AI-generated summary.

        Args:
            guid: The paper's GUID.
            summary: The generated summary to save.
        """
        ...

    async def update_deep_analysis(self, guid: str, analysis: str) -> None:
        """Update a paper's deep analysis result.

        Args:
            guid: The paper's GUID.
            analysis: The deep analysis text.
        """
        ...

    async def get_papers_by_fetched_date(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[Paper]:
        """Get papers by when they were fetched (not published).

        Args:
            start_date: Start of the fetch date range.
            end_date: End of the fetch date range.

        Returns:
            List of papers fetched within the range.

        Reason: Enables querying papers by fetch date to support
        manual daily task triggering for today's papers.
        """
        ...

    async def reset_notification_status(self, guids: list[str]) -> None:
        """Reset notification status for specified papers.

        Args:
            guids: List of paper GUIDs to reset.

        Reason: Allows re-sending notifications for papers that
        were already notified, useful for manual re-triggers.
        """
        ...

    async def close(self) -> None:
        """Close the storage connection."""
        ...
