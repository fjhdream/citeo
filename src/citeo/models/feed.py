"""Feed configuration models."""

from typing import List

from pydantic import BaseModel, Field, HttpUrl


class FeedConfig(BaseModel):
    """RSS feed source configuration."""

    source_id: str = Field(..., description="Unique source identifier")
    name: str = Field(..., description="Human-readable name")
    url: HttpUrl = Field(..., description="RSS feed URL")
    parser_type: str = Field(default="arxiv", description="Parser type to use")
    enabled: bool = Field(default=True)

    # Filter configuration
    include_categories: List[str] = Field(
        default_factory=list,
        description="Categories to include (empty means all)",
    )
    exclude_announce_types: List[str] = Field(
        default_factory=lambda: ["replace"],
        description="Announcement types to exclude",
    )

    # AI processing options
    enable_translation: bool = Field(default=True)
    enable_deep_analysis: bool = Field(default=False)


class FeedCollection(BaseModel):
    """Collection of feed configurations."""

    feeds: List[FeedConfig] = Field(default_factory=list)

    def get_enabled_feeds(self) -> List[FeedConfig]:
        """Return only enabled feeds."""
        return [f for f in self.feeds if f.enabled]
