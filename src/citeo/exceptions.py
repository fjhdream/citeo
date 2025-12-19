"""Custom exceptions for Citeo application.

Provides a structured exception hierarchy for different error scenarios.
"""


class CiteoError(Exception):
    """Base exception class for all Citeo errors."""

    pass


class FetchError(CiteoError):
    """Raised when RSS feed fetching fails.

    Attributes:
        source_id: The identifier of the feed source that failed.
    """

    def __init__(self, source_id: str, message: str):
        self.source_id = source_id
        super().__init__(f"Failed to fetch {source_id}: {message}")


class ParseError(CiteoError):
    """Raised when RSS content parsing fails.

    Attributes:
        source_id: The identifier of the feed source with parse error.
    """

    def __init__(self, source_id: str, message: str):
        self.source_id = source_id
        super().__init__(f"Failed to parse {source_id}: {message}")


class AIProcessingError(CiteoError):
    """Raised when AI processing (summarization/translation) fails.

    Attributes:
        paper_guid: The GUID of the paper that failed processing.
    """

    def __init__(self, paper_guid: str, message: str):
        self.paper_guid = paper_guid
        super().__init__(f"AI processing failed for {paper_guid}: {message}")


class NotificationError(CiteoError):
    """Raised when notification delivery fails.

    Attributes:
        channel: The notification channel that failed (e.g., 'telegram').
    """

    def __init__(self, channel: str, message: str):
        self.channel = channel
        super().__init__(f"Notification failed via {channel}: {message}")


class StorageError(CiteoError):
    """Raised when database/storage operations fail."""

    pass


class PDFDownloadError(CiteoError):
    """Raised when PDF download fails.

    Attributes:
        arxiv_id: The arXiv ID of the paper.
    """

    def __init__(self, arxiv_id: str, message: str):
        self.arxiv_id = arxiv_id
        super().__init__(f"PDF download failed for {arxiv_id}: {message}")
