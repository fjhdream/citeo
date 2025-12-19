"""Storage factory for creating database instances.

Provides a factory function to create appropriate storage based on configuration.
"""

from citeo.config.settings import Settings
from citeo.storage.base import PaperStorage
from citeo.storage.d1 import D1PaperStorage
from citeo.storage.sqlite import SQLitePaperStorage


def create_storage(settings: Settings) -> PaperStorage:
    """Create a storage instance based on configuration.

    Args:
        settings: Application settings.

    Returns:
        PaperStorage instance (SQLite or D1).

    Raises:
        ValueError: If database type is unsupported or configuration is invalid.

    Reason: Factory pattern allows easy switching between database types
    while maintaining the same interface throughout the application.
    """
    db_type = settings.db_type.lower()

    if db_type == "sqlite":
        return SQLitePaperStorage(settings.db_path)

    elif db_type == "d1":
        # Validate D1 configuration
        if not settings.d1_account_id:
            raise ValueError("D1_ACCOUNT_ID is required when DB_TYPE=d1")
        if not settings.d1_database_id:
            raise ValueError("D1_DATABASE_ID is required when DB_TYPE=d1")
        if not settings.d1_api_token:
            raise ValueError("D1_API_TOKEN is required when DB_TYPE=d1")

        return D1PaperStorage(
            account_id=settings.d1_account_id,
            database_id=settings.d1_database_id,
            api_token=settings.d1_api_token.get_secret_value(),
        )

    else:
        raise ValueError(f"Unsupported database type: {db_type}. " f"Supported types: sqlite, d1")
