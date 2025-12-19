"""Configuration management using pydantic-settings.

Supports environment variables and .env file loading.
"""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration.

    Reason: Using pydantic-settings for type-safe config management,
    supporting environment variable override for different deployment environments.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),  # .env.local overrides .env
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra env vars like OPENAI_AGENTS_DISABLE_TRACING
    )

    # Application
    app_name: str = "citeo"
    debug: bool = False
    log_level: str = "INFO"
    log_json: bool = False  # Set True in production for structured logs

    # Database
    db_type: str = Field(
        default="sqlite",
        description="Database type: sqlite or d1",
    )
    db_path: Path = Field(
        default=Path("data/citeo.db"),
        description="SQLite database path (used when db_type=sqlite)",
    )

    # Cloudflare D1 Database (used when db_type=d1)
    d1_account_id: str | None = Field(
        default=None,
        description="Cloudflare account ID",
    )
    d1_database_id: str | None = Field(
        default=None,
        description="Cloudflare D1 database ID",
    )
    d1_api_token: SecretStr | None = Field(
        default=None,
        description="Cloudflare API token with D1 permissions",
    )

    # OpenAI
    openai_api_key: SecretStr = Field(..., description="OpenAI API Key")
    openai_base_url: str | None = Field(
        default=None,
        description="Custom OpenAI API base URL (for compatible APIs)",
    )
    openai_model: str = "gpt-4o"
    openai_timeout: int = 60

    # OpenAI Tracing (optional, for Agents SDK tracing feature)
    openai_tracing_api_key: SecretStr | None = Field(
        default=None,
        description="Separate OpenAI API key for tracing (if using custom base URL)",
    )
    openai_tracing_enabled: bool = Field(
        default=True,
        description="Enable OpenAI Agents SDK tracing",
    )

    # Telegram (optional)
    telegram_bot_token: SecretStr | None = Field(default=None, description="Telegram Bot Token")
    telegram_chat_id: str | None = Field(default=None, description="Target Chat ID")

    # Feishu/Lark (optional)
    feishu_webhook_url: SecretStr | None = Field(
        default=None,
        description="Feishu bot webhook URL",
    )
    feishu_secret: SecretStr | None = Field(
        default=None,
        description="Feishu webhook signing secret (optional)",
    )

    # Notifier selection (supports multiple: "telegram,feishu")
    notifier_types: list[str] = Field(
        default=["telegram"],
        description="Notification channels to use (comma-separated)",
    )

    # RSS
    rss_fetch_timeout: int = 30
    rss_user_agent: str = "Citeo/1.0 (arXiv RSS Reader)"

    # Schedule
    daily_fetch_hour: int = Field(default=8, ge=0, le=23)
    daily_fetch_minute: int = Field(default=0, ge=0, le=59)

    # AI processing
    enable_translation: bool = True
    enable_deep_analysis: bool = False
    max_papers_per_batch: int = 50
    ai_max_concurrent: int = Field(
        default=5,
        ge=1,
        description="Maximum concurrent AI processing tasks (to avoid rate limits)",
    )
    min_notification_score: float = Field(
        default=8.0,
        ge=1.0,
        le=10.0,
        description="Minimum programmer recommendation score for notification (1-10)",
    )

    # Feed URLs (simple config, can also use database for complex scenarios)
    feed_urls: list[str] = Field(
        default=["https://rss.arxiv.org/rss/cs.AI"],
        description="RSS feed URLs to subscribe",
    )

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Authentication
    auth_enabled: bool = Field(
        default=True,
        description="Enable API authentication (set False to disable all auth)",
    )
    auth_api_key: SecretStr | None = Field(
        default=None,
        description="API key for X-API-Key header authentication",
    )
    auth_jwt_secret: SecretStr | None = Field(
        default=None,
        description="Secret key for JWT token signing (min 32 chars recommended)",
    )
    auth_jwt_access_token_expiry_minutes: int = Field(
        default=60,
        ge=1,
        le=1440,  # Max 24 hours
        description="Access token expiry time in minutes (for API access)",
    )
    auth_jwt_refresh_token_expiry_days: int = Field(
        default=7,
        ge=1,
        le=30,  # Max 30 days
        description="Refresh token expiry time in days (for token refresh)",
    )

    # Rate Limiting
    rate_limit_analyze_requests: int = Field(
        default=10,
        ge=1,
        description="Max /analyze requests per window",
    )
    rate_limit_analyze_window: int = Field(
        default=60,
        ge=1,
        description="Rate limit window in seconds",
    )


# Global singleton instance
# Reason: Settings are loaded once and shared across the application
settings = Settings()
