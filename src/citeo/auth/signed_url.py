"""Signed URL generation and verification for notification links.

Provides secure, one-time-use signed URLs for triggering PDF deep analysis
from notification platforms (Telegram, Feishu) without exposing API keys.
"""

import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass
from datetime import datetime

import aiosqlite
import structlog

from citeo.config.settings import settings

logger = structlog.get_logger()


@dataclass
class SignedURLVerification:
    """Result of signed URL verification."""

    valid: bool
    arxiv_id: str | None = None
    platform: str | None = None
    error: str | None = None


class NonceStorage:
    """Manage one-time-use nonce state with SQLite storage.

    Reason: Store nonce state in SQLite to track used nonces and prevent
    replay attacks. Supports automatic cleanup of expired nonces.
    """

    def __init__(self, db_path: str):
        """Initialize nonce storage.

        Args:
            db_path: Path to SQLite database.
        """
        self._db_path = db_path

    async def _init_table(self) -> None:
        """Create nonce table if it doesn't exist."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS signed_url_nonces (
                    nonce TEXT PRIMARY KEY,
                    created_at INTEGER NOT NULL,
                    consumed_at INTEGER,
                    arxiv_id TEXT NOT NULL,
                    platform TEXT NOT NULL
                )
                """
            )
            # Index for cleanup queries
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_nonces_created_at
                ON signed_url_nonces(created_at)
                """
            )
            await db.commit()

    async def is_nonce_used(self, nonce: str) -> bool:
        """Check if a nonce has been used.

        Args:
            nonce: The nonce to check.

        Returns:
            True if nonce exists (already used), False otherwise.
        """
        await self._init_table()

        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT consumed_at FROM signed_url_nonces WHERE nonce = ?",
                (nonce,),
            ) as cursor:
                row = await cursor.fetchone()
                return row is not None

    async def mark_nonce_used(self, nonce: str, arxiv_id: str, platform: str) -> bool:
        """Mark a nonce as used.

        Args:
            nonce: The nonce to mark as used.
            arxiv_id: Associated arXiv paper ID.
            platform: Platform that triggered the request.

        Returns:
            True if successfully marked, False if already exists.
        """
        await self._init_table()

        now = int(time.time())

        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    """
                    INSERT INTO signed_url_nonces
                    (nonce, created_at, consumed_at, arxiv_id, platform)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (nonce, now, now, arxiv_id, platform),
                )
                await db.commit()
                return True
        except aiosqlite.IntegrityError:
            # Nonce already exists
            logger.warning("Nonce already used", nonce=nonce)
            return False

    async def cleanup_expired_nonces(self, expiry_hours: int = 168) -> int:
        """Remove expired nonces from storage.

        Args:
            expiry_hours: Nonces older than this are deleted (default: 7 days).

        Returns:
            Number of nonces deleted.
        """
        await self._init_table()

        cutoff = int(time.time()) - (expiry_hours * 3600)

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM signed_url_nonces WHERE created_at < ?",
                (cutoff,),
            )
            await db.commit()
            deleted = cursor.rowcount

        if deleted > 0:
            logger.info("Cleaned up expired nonces", count=deleted)

        return deleted


class SignedURLGenerator:
    """Generate and verify signed URLs for deep analysis triggers.

    Reason: Centralized signing logic ensures consistency and security.
    Uses HMAC-SHA256 with nonce for one-time-use URLs.
    """

    def __init__(self, secret: str, expiry_hours: int = 24, nonce_storage: NonceStorage = None):
        """Initialize with signing secret and expiry time.

        Args:
            secret: Signing secret key (min 32 chars recommended).
            expiry_hours: URL expiry time in hours (default: 24).
            nonce_storage: NonceStorage instance for tracking used nonces.
        """
        if len(secret) < 16:
            raise ValueError("Signing secret must be at least 16 characters")

        self._secret = secret
        self._expiry_seconds = expiry_hours * 3600
        self._nonce_storage = nonce_storage

    def generate_analysis_url(self, arxiv_id: str, platform: str) -> str:
        """Generate signed URL for triggering analysis.

        Args:
            arxiv_id: arXiv paper ID (e.g., "2512.14709").
            platform: Platform identifier ("telegram" or "feishu").

        Returns:
            Full URL with signature and nonce.
        """
        timestamp = int(time.time())
        nonce = str(uuid.uuid4())  # Generate unique nonce
        signature = self._compute_signature(arxiv_id, platform, timestamp, nonce)

        base_url = settings.api_base_url.rstrip("/")
        url = (
            f"{base_url}/api/papers/trigger-analysis?"
            f"arxiv_id={arxiv_id}&"
            f"platform={platform}&"
            f"timestamp={timestamp}&"
            f"nonce={nonce}&"
            f"signature={signature}"
        )

        logger.debug(
            "Generated signed URL",
            arxiv_id=arxiv_id,
            platform=platform,
            expires_at=datetime.fromtimestamp(timestamp + self._expiry_seconds).isoformat(),
        )

        return url

    async def verify_url(
        self, arxiv_id: str, platform: str, timestamp: int, nonce: str, signature: str
    ) -> SignedURLVerification:
        """Verify signed URL parameters.

        Args:
            arxiv_id: arXiv paper ID.
            platform: Platform identifier.
            timestamp: Unix timestamp from URL.
            nonce: Unique nonce from URL.
            signature: HMAC signature from URL.

        Returns:
            SignedURLVerification with validation result.
        """
        # Check timestamp validity
        current_time = int(time.time())

        # Reject future timestamps (clock skew tolerance: 5 minutes)
        if timestamp > current_time + 300:
            return SignedURLVerification(valid=False, error="Invalid timestamp (future)")

        # Check expiry
        if current_time - timestamp > self._expiry_seconds:
            expiry_hours = self._expiry_seconds // 3600
            return SignedURLVerification(
                valid=False, error=f"URL expired (valid for {expiry_hours}h)"
            )

        # Validate platform
        if platform not in ["telegram", "feishu"]:
            return SignedURLVerification(valid=False, error=f"Invalid platform: {platform}")

        # Check if nonce already used
        if self._nonce_storage:
            if await self._nonce_storage.is_nonce_used(nonce):
                return SignedURLVerification(valid=False, error="URL already used (nonce consumed)")

        # Verify signature
        expected_sig = self._compute_signature(arxiv_id, platform, timestamp, nonce)

        # Constant-time comparison (prevent timing attacks)
        if not hmac.compare_digest(signature, expected_sig):
            return SignedURLVerification(valid=False, error="Invalid signature")

        return SignedURLVerification(valid=True, arxiv_id=arxiv_id, platform=platform)

    def _compute_signature(self, arxiv_id: str, platform: str, timestamp: int, nonce: str) -> str:
        """Compute HMAC-SHA256 signature.

        Args:
            arxiv_id: arXiv paper ID.
            platform: Platform identifier.
            timestamp: Unix timestamp.
            nonce: Unique nonce.

        Returns:
            Hex-encoded HMAC signature.
        """
        # Canonical string includes all parameters
        # Reason: Including nonce in signature prevents tampering
        canonical = f"{arxiv_id}|{platform}|{timestamp}|{nonce}"

        return hmac.new(
            key=self._secret.encode("utf-8"),
            msg=canonical.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()


# Global instance (initialized lazily)
_url_generator: SignedURLGenerator | None = None


def get_url_generator() -> SignedURLGenerator:
    """Get or create global URL generator instance.

    Raises:
        ValueError: If SIGNED_URL_SECRET not configured.

    Returns:
        SignedURLGenerator instance.
    """
    global _url_generator

    if _url_generator is None:
        if not settings.signed_url_secret:
            raise ValueError(
                "SIGNED_URL_SECRET not configured. "
                "Required for generating analysis links in notifications."
            )

        # Create nonce storage
        nonce_storage = NonceStorage(str(settings.db_path))

        _url_generator = SignedURLGenerator(
            secret=settings.signed_url_secret.get_secret_value(),
            expiry_hours=settings.signed_url_expiry_hours,
            nonce_storage=nonce_storage,
        )

        logger.info(
            "Signed URL generator initialized",
            expiry_hours=settings.signed_url_expiry_hours,
        )

    return _url_generator
