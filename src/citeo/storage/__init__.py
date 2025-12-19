"""Storage package."""

from citeo.storage.base import PaperStorage
from citeo.storage.sqlite import SQLitePaperStorage

__all__ = [
    "PaperStorage",
    "SQLitePaperStorage",
]
