"""Configuration management using pydantic-settings.

Supports environment variables and .env file loading.
"""

from pathlib import Path
from typing import List

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
    )

    # Application
    app_name: str = "citeo"
    debug: bool = False
    log_level: str = "INFO"
    log_json: bool = False  # Set True in production for structured logs

    # Database
    db_path: Path = Field(
        default=Path("data/citeo.db"),
        description="SQLite database path",
    )

    # OpenAI
    openai_api_key: SecretStr = Field(..., description="OpenAI API Key")
    openai_base_url: str | None = Field(
        default=None,
        description="Custom OpenAI API base URL (for compatible APIs)",
    )
    openai_model: str = "gpt-4o"
    openai_timeout: int = 60

    # Telegram
    telegram_bot_token: SecretStr = Field(..., description="Telegram Bot Token")
    telegram_chat_id: str = Field(..., description="Target Chat ID")

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

    # Feed URLs (simple config, can also use database for complex scenarios)
    feed_urls: List[str] = Field(
        default=["https://rss.arxiv.org/rss/cs.AI"],
        description="RSS feed URLs to subscribe",
    )

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000


# Global singleton instance
# Reason: Settings are loaded once and shared across the application
settings = Settings()
