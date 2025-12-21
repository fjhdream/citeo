"""Paper data models for arXiv papers and AI-generated summaries."""

from datetime import datetime

from pydantic import BaseModel, Field, computed_field


class PaperSummary(BaseModel):
    """AI-generated paper summary with translation.

    Contains Chinese translation and key insights extracted by AI.
    """

    title_zh: str = Field(..., description="Chinese translated title")
    abstract_zh: str = Field(..., description="Chinese translated abstract")
    key_points: list[str] = Field(
        default_factory=list,
        description="Key points in Chinese (3-5 items)",
    )
    relevance_score: float = Field(
        default=1.0,
        ge=1.0,
        le=10.0,
        description="Programmer recommendation score for sorting (1-10)",
    )
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # Optional: PDF deep analysis result
    deep_analysis: str | None = Field(default=None)


class Paper(BaseModel):
    """arXiv paper data model.

    Represents a single paper item from RSS feed with optional AI summary.
    """

    # Core fields from RSS
    guid: str = Field(..., description="Unique identifier, e.g., oai:arXiv.org:2512.14709v1")
    arxiv_id: str = Field(..., description="arXiv ID, e.g., 2512.14709")
    title: str = Field(..., description="Paper title")
    abstract: str = Field(..., description="Paper abstract")
    authors: list[str] = Field(default_factory=list, description="Author list")
    categories: list[str] = Field(default_factory=list, description="Category list")
    announce_type: str = Field(default="new", description="Announcement type: new/cross/replace")
    published_at: datetime = Field(..., description="Publication time")

    # URL
    abs_url: str = Field(..., description="Abstract page URL")

    # Metadata
    source_id: str = Field(..., description="Source identifier, e.g., arxiv.cs.AI")
    fetched_at: datetime = Field(default_factory=datetime.utcnow)

    # AI processing result (optional, populated after processing)
    summary: PaperSummary | None = Field(default=None)

    # Status flags
    is_notified: bool = Field(default=False, description="Whether notification was sent")
    notified_at: datetime | None = Field(default=None)

    @computed_field
    @property
    def pdf_url(self) -> str:
        """Compute PDF URL from abs_url.

        Reason: PDF URL follows a fixed pattern, no need to store separately.
        """
        return self.abs_url.replace("/abs/", "/pdf/") + ".pdf"

    model_config = {"frozen": False}  # Allow modification (adding summary, etc.)
