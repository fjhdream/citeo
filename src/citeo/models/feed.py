"""Feed configuration models."""

from pydantic import BaseModel, Field, HttpUrl


class FeedConfig(BaseModel):
    """RSS feed source configuration."""

    source_id: str = Field(..., description="Unique source identifier")
    name: str = Field(..., description="Human-readable name")
    url: HttpUrl = Field(..., description="RSS feed URL")
    parser_type: str = Field(default="arxiv", description="Parser type to use")
    enabled: bool = Field(default=True)

    # Filter configuration
    include_categories: list[str] = Field(
        default_factory=list,
        description="Categories to include (empty means all)",
    )
    exclude_announce_types: list[str] = Field(
        default_factory=lambda: ["replace"],
        description="Announcement types to exclude",
    )

    # AI processing options
    enable_translation: bool = Field(default=True)
    enable_deep_analysis: bool = Field(default=False)


class FeedCollection(BaseModel):
    """Collection of feed configurations."""

    feeds: list[FeedConfig] = Field(default_factory=list)

    def get_enabled_feeds(self) -> list[FeedConfig]:
        """Return only enabled feeds."""
        return [f for f in self.feeds if f.enabled]
