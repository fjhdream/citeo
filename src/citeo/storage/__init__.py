"""Storage package."""

from citeo.storage.base import PaperStorage
from citeo.storage.d1 import D1PaperStorage
from citeo.storage.factory import create_storage
from citeo.storage.sqlite import SQLitePaperStorage

__all__ = [
    "PaperStorage",
    "SQLitePaperStorage",
    "D1PaperStorage",
    "create_storage",
]
