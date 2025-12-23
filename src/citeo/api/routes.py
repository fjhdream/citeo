"""API routes for Citeo.

Provides REST API endpoints for PDF analysis and paper queries.
"""

import re
from datetime import datetime, timedelta
from pathlib import Path

import markdown
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from citeo.auth.dependencies import require_auth
from citeo.auth.exceptions import RateLimitExceededError
from citeo.auth.models import AuthUser
from citeo.auth.rate_limiter import (
    InMemoryRateLimiter,
    RateLimitConfig,
    get_analyze_rate_limiter,
)
from citeo.auth.signed_url import get_url_generator
from citeo.config.settings import Settings
from citeo.notifiers.base import Notifier
from citeo.notifiers.factory import create_notifier
from citeo.services.pdf_service import PDFService
from citeo.storage import PaperStorage, create_storage

logger = structlog.get_logger()

router = APIRouter(prefix="/api", tags=["papers"])

# Initialize Jinja2 templates
# Reason: Template-based rendering for public web views of deep analysis
_templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

# Service instances (will be initialized on app startup)
_storage: PaperStorage | None = None
_pdf_service: PDFService | None = None
_notifier: Notifier | None = None


def init_services(settings: Settings) -> None:
    """Initialize API services.

    Must be called before API routes can be used.

    Args:
        settings: Application settings.
    """
    global _storage, _pdf_service, _notifier
    _storage = create_storage(settings)

    # Initialize URL generator if configured
    url_generator = None
    try:
        from citeo.auth.signed_url import get_url_generator

        url_generator = get_url_generator()
        logger.info("URL generator initialized for API services")
    except ValueError as e:
        logger.warning("URL generator not configured, analysis links disabled", error=str(e))

    # Create notifier if configured
    # Reason: Notifier is optional, only create if notifier_types is configured
    try:
        if settings.notifier_types:
            _notifier = create_notifier(
                notifier_types=settings.notifier_types,
                telegram_token=(
                    settings.telegram_bot_token.get_secret_value()
                    if settings.telegram_bot_token
                    else None
                ),
                telegram_chat_id=settings.telegram_chat_id,
                feishu_webhook_url=(
                    settings.feishu_webhook_url.get_secret_value()
                    if settings.feishu_webhook_url
                    else None
                ),
                feishu_secret=(
                    settings.feishu_secret.get_secret_value() if settings.feishu_secret else None
                ),
                url_generator=url_generator,
            )
    except ValueError as e:
        # Log warning but don't fail initialization
        logger.warning("Failed to create notifier", error=str(e))
        _notifier = None

    _pdf_service = PDFService(_storage, notifier=_notifier)


def get_pdf_service() -> PDFService:
    """Get PDF service instance."""
    if _pdf_service is None:
        raise RuntimeError("Services not initialized. Call init_services first.")
    return _pdf_service


def get_storage() -> PaperStorage:
    """Get storage instance."""
    if _storage is None:
        raise RuntimeError("Services not initialized. Call init_services first.")
    return _storage


def get_notifier() -> Notifier | None:
    """Get notifier instance.

    Returns:
        Notifier instance or None if not configured.
    """
    return _notifier


# Helper functions for date handling


def _get_today_range() -> tuple[datetime, datetime]:
    """Get today's date range (00:00:00 to 23:59:59 UTC).

    Reason: Centralized date range calculation for default queries.
    """
    now_utc = datetime.utcnow()
    start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def _parse_date(date_str: str) -> datetime:
    """Parse date string to datetime object (UTC).

    Supports: YYYY-MM-DD, ISO 8601.
    Raises: ValueError if invalid format.
    """
    try:
        if len(date_str) == 10:  # YYYY-MM-DD
            return datetime.strptime(date_str, "%Y-%m-%d")
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        raise ValueError(f"Invalid date format: {date_str}. Use YYYY-MM-DD")


def _validate_date_params(
    date: str | None,
    start_date: str | None,
    end_date: str | None,
) -> tuple[datetime, datetime]:
    """Validate and normalize date parameters.

    Returns: (start_datetime, end_datetime) tuple.
    Raises: HTTPException(400) if invalid.

    Reason: Single source of truth for date validation logic.
    """
    # Check mutually exclusive parameters
    if date and (start_date or end_date):
        raise HTTPException(
            status_code=400,
            detail="Cannot use both 'date' and 'start_date/end_date'",
        )

    # Single date query
    if date:
        try:
            query_date = _parse_date(date)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        start_dt = query_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = start_dt + timedelta(days=1)
        return start_dt, end_dt

    # Date range query
    if start_date or end_date:
        if not (start_date and end_date):
            raise HTTPException(
                status_code=400,
                detail="Both 'start_date' and 'end_date' required for range query",
            )

        try:
            start_dt = _parse_date(start_date)
            end_dt = _parse_date(end_date)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        if start_dt > end_dt:
            raise HTTPException(
                status_code=400,
                detail="'start_date' must be before or equal to 'end_date'",
            )

        # Extend end_dt to end of day
        end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        return start_dt, end_dt

    # Default: today
    return _get_today_range()


# Request/Response models


class AnalyzeRequest(BaseModel):
    """Request to analyze a paper's PDF."""

    arxiv_id: str = Field(..., description="arXiv paper ID (e.g., 2512.14709)")


class AnalyzeResponse(BaseModel):
    """Response from PDF analysis."""

    arxiv_id: str
    status: str = Field(..., description="Status: completed, cached, processing, error")
    analysis: str | None = Field(default=None, description="Analysis content")
    error: str | None = Field(default=None, description="Error message if failed")


class PaperResponse(BaseModel):
    """Paper information response."""

    arxiv_id: str
    title: str
    title_zh: str | None = None
    abstract: str
    abstract_zh: str | None = None
    authors: list[str]
    categories: list[str]
    abs_url: str
    pdf_url: str
    has_summary: bool
    has_deep_analysis: bool


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str


class PaperListItemResponse(BaseModel):
    """Single paper item in list response."""

    arxiv_id: str
    title: str
    title_zh: str | None = None
    abstract: str
    abstract_zh: str | None = None
    authors: list[str]
    categories: list[str]
    published_at: datetime
    abs_url: str
    pdf_url: str
    has_summary: bool
    has_deep_analysis: bool


class PaperListResponse(BaseModel):
    """Paper list response with pagination."""

    total: int = Field(..., description="Total papers matching criteria")
    count: int = Field(..., description="Number of papers in this response")
    limit: int = Field(..., description="Page size limit")
    offset: int = Field(..., description="Pagination offset")
    papers: list[PaperListItemResponse] = Field(..., description="List of papers")
    query_date: str | None = Field(None, description="Query date (single date mode)")
    query_range: dict | None = Field(None, description="Query range (range mode)")


class ResendResponse(BaseModel):
    """Paper resend notification response."""

    status: str = Field(..., description="Operation status (success/error)")
    arxiv_id: str = Field(..., description="arXiv paper ID")
    title: str = Field(..., description="Paper title")
    notified_channels: int = Field(..., description="Number of notification channels notified")
    message: str = Field(..., description="Human-readable status message")


class TriggerDailyTaskResponse(BaseModel):
    """Response from manual daily task trigger."""

    status: str = Field(
        ...,
        description="Status: fetched_and_notified, processed_and_notified, "
        "re_notified, already_notified",
    )
    papers_total: int = Field(..., description="Total papers fetched today")
    papers_fetched: int = Field(..., description="Newly fetched papers (if pipeline ran)")
    papers_new: int = Field(..., description="New papers after dedup")
    papers_processed: int = Field(..., description="Papers processed with AI")
    papers_notified: int = Field(..., description="Papers actually notified")
    message: str = Field(..., description="Human-readable message")
    errors: list[str] = Field(default_factory=list, description="Error messages if any")


# Background task storage
_analysis_tasks: dict[str, str] = {}  # arxiv_id -> status


async def check_analyze_rate_limit(user: AuthUser = Depends(require_auth)) -> AuthUser:
    """Check rate limit for analyze endpoint.

    Reason: /analyze triggers expensive OpenAI calls, needs protection.
    """
    rate_limiter = get_analyze_rate_limiter()
    try:
        rate_limiter.check_rate_limit(user.user_id)
    except RateLimitExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Retry after {e.retry_after} seconds.",
            headers={"Retry-After": str(e.retry_after)},
        )
    return user


async def _run_analysis_background(arxiv_id: str, force: bool = False) -> None:
    """Run PDF analysis in background.

    Args:
        arxiv_id: arXiv paper ID.
        force: If True, force re-analysis even if cached.
    """
    _analysis_tasks[arxiv_id] = "processing"
    try:
        result = await get_pdf_service().analyze_paper(arxiv_id, force=force)
        _analysis_tasks[arxiv_id] = result.get("status", "completed")
    except Exception as e:
        _analysis_tasks[arxiv_id] = f"error: {e}"


async def _run_analysis_background_with_platform(
    arxiv_id: str, platform: str, force: bool = False
) -> None:
    """Run PDF analysis in background with platform-specific notification.

    Args:
        arxiv_id: arXiv paper ID.
        platform: Platform that triggered analysis (telegram, feishu).
        force: If True, force re-analysis even if cached.

    Reason: Isolate notifications to the triggering platform only.
    """
    _analysis_tasks[arxiv_id] = "processing"

    try:
        # Get services
        pdf_service = get_pdf_service()
        storage = get_storage()

        # Perform analysis without sending notification in service
        result = await pdf_service.analyze_paper(arxiv_id, force=force, skip_notification=True)

        _analysis_tasks[arxiv_id] = result.get("status", "completed")

        # Send platform-specific notification on success
        if result["status"] == "completed":
            paper = await storage.get_paper_by_arxiv_id(arxiv_id)
            if paper and paper.summary and paper.summary.deep_analysis:
                # Get platform-specific notifier
                notifier = _get_platform_notifier(platform)
                if notifier:
                    await notifier.send_deep_analysis(paper)
                    logger.info(
                        "Platform-specific analysis notification sent",
                        arxiv_id=arxiv_id,
                        platform=platform,
                    )
                else:
                    logger.warning(
                        "No notifier found for platform",
                        platform=platform,
                    )

    except Exception as e:
        _analysis_tasks[arxiv_id] = f"error: {e}"
        logger.error(
            "Background analysis failed",
            arxiv_id=arxiv_id,
            platform=platform,
            error=str(e),
        )


def _get_platform_notifier(platform: str) -> Notifier | None:
    """Get notifier instance for specific platform.

    Args:
        platform: Platform identifier (telegram or feishu).

    Returns:
        Platform-specific notifier instance, or None if not found.

    Reason: Isolate notifications to the triggering platform only.
    When MultiNotifier is used, extract the specific platform notifier.
    """
    if not _notifier:
        return None

    # Import notifier types
    from citeo.notifiers.feishu import FeishuNotifier
    from citeo.notifiers.multi import MultiNotifier
    from citeo.notifiers.telegram import TelegramNotifier

    # If _notifier is MultiNotifier, extract the specific platform notifier
    if isinstance(_notifier, MultiNotifier):
        # Access internal notifiers list
        for n in _notifier._notifiers:
            if platform == "telegram" and isinstance(n, TelegramNotifier):
                return n
            elif platform == "feishu" and isinstance(n, FeishuNotifier):
                return n
        return None
    else:
        # Single notifier - check if it matches platform
        if platform == "telegram" and isinstance(_notifier, TelegramNotifier):
            return _notifier
        elif platform == "feishu" and isinstance(_notifier, FeishuNotifier):
            return _notifier
        return None


# Routes


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok", version="0.1.0")


@router.get("/papers/trigger-analysis")
async def trigger_analysis_signed(
    arxiv_id: str = Query(..., description="arXiv paper ID"),
    platform: str = Query(..., description="Platform identifier (telegram, feishu)"),
    timestamp: int = Query(..., description="Unix timestamp"),
    nonce: str = Query(..., description="Unique nonce (UUID)"),
    signature: str = Query(..., description="HMAC signature"),
    background_tasks: BackgroundTasks = None,
) -> dict:
    """Trigger PDF analysis via signed URL (no authentication required).

    This endpoint is called from notification platforms (Telegram, Feishu)
    when users click the "深度分析" link. The URL is signed with HMAC-SHA256
    and includes a one-time-use nonce to prevent replay attacks.

    Args:
        arxiv_id: arXiv paper ID.
        platform: Platform that triggered the request.
        timestamp: URL generation timestamp.
        nonce: One-time-use unique identifier.
        signature: HMAC-SHA256 signature of parameters.

    Returns:
        Status dict indicating processing has started.

    Raises:
        HTTPException(401): If signature verification fails.
        HTTPException(404): If paper not found.
    """
    # 1. Verify signed URL
    try:
        url_generator = get_url_generator()
    except ValueError as e:
        logger.error("URL generator not configured", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Signed URL feature not configured on server",
        )

    verification = await url_generator.verify_url(
        arxiv_id=arxiv_id,
        platform=platform,
        timestamp=timestamp,
        nonce=nonce,
        signature=signature,
    )

    if not verification.valid:
        logger.warning(
            "Signed URL verification failed",
            arxiv_id=arxiv_id,
            platform=platform,
            error=verification.error,
        )
        raise HTTPException(
            status_code=401,
            detail=f"Invalid signed URL: {verification.error}",
        )

    # 2. Mark nonce as used (prevent replay)
    nonce_storage = url_generator._nonce_storage
    if nonce_storage:
        success = await nonce_storage.mark_nonce_used(nonce, arxiv_id, platform)
        if not success:
            # Nonce already used
            return {
                "arxiv_id": arxiv_id,
                "status": "already_triggered",
                "message": "分析已触发，请勿重复点击",
            }

    # 3. Check if paper exists
    storage = get_storage()
    paper = await storage.get_paper_by_arxiv_id(arxiv_id)
    if not paper:
        raise HTTPException(
            status_code=404,
            detail=f"Paper with arXiv ID {arxiv_id} not found",
        )

    # 4. Check if already processing
    if arxiv_id in _analysis_tasks and _analysis_tasks[arxiv_id] == "processing":
        return {
            "arxiv_id": arxiv_id,
            "status": "processing",
            "message": "分析正在进行中，完成后将推送通知",
        }

    # 5. Start background analysis with platform context
    background_tasks.add_task(
        _run_analysis_background_with_platform,
        arxiv_id=arxiv_id,
        platform=platform,
        force=False,  # Don't force re-analysis from signed URL
    )

    logger.info(
        "Signed URL analysis triggered",
        arxiv_id=arxiv_id,
        platform=platform,
    )

    # 6. Return immediately
    return {
        "arxiv_id": arxiv_id,
        "status": "processing",
        "message": "分析已开始，完成后将推送通知到"
        + ("Telegram" if platform == "telegram" else "飞书"),
    }


@router.post("/papers/{arxiv_id}/analyze", response_model=AnalyzeResponse)
async def analyze_paper(
    arxiv_id: str,
    background_tasks: BackgroundTasks,
    user: AuthUser = Depends(check_analyze_rate_limit),
    sync: bool = False,
    force: bool = Query(False, description="Force re-analysis even if cached"),
) -> AnalyzeResponse:
    """Trigger PDF deep analysis for a paper.

    Args:
        arxiv_id: arXiv paper ID.
        sync: If True, wait for analysis to complete. Otherwise run in background.
        force: If True, force re-analysis even if cached result exists.

    Returns:
        Analysis result or processing status.
    """
    pdf_service = get_pdf_service()

    if sync:
        # Synchronous mode: wait for completion
        try:
            result = await pdf_service.analyze_paper(arxiv_id, force=force)
            return AnalyzeResponse(
                arxiv_id=arxiv_id,
                status=result["status"],
                analysis=result.get("analysis"),
                error=result.get("error"),
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
    else:
        # Async mode: run in background
        # Check if paper exists first
        storage = get_storage()
        paper = await storage.get_paper_by_arxiv_id(arxiv_id)
        if not paper:
            raise HTTPException(
                status_code=404,
                detail=f"Paper with arXiv ID {arxiv_id} not found",
            )

        # Check if already processing (skip check if force=True to allow re-queueing)
        if not force and arxiv_id in _analysis_tasks and _analysis_tasks[arxiv_id] == "processing":
            return AnalyzeResponse(
                arxiv_id=arxiv_id,
                status="processing",
            )

        # Start background task
        background_tasks.add_task(_run_analysis_background, arxiv_id, force)

        return AnalyzeResponse(
            arxiv_id=arxiv_id,
            status="processing",
        )


@router.get("/papers/{arxiv_id}/analysis", response_model=AnalyzeResponse)
async def get_analysis(arxiv_id: str, user: AuthUser = Depends(require_auth)) -> AnalyzeResponse:
    """Get PDF analysis result for a paper.

    Args:
        arxiv_id: arXiv paper ID.

    Returns:
        Analysis result or status.
    """
    pdf_service = get_pdf_service()

    result = await pdf_service.get_analysis(arxiv_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Paper with arXiv ID {arxiv_id} not found",
        )

    # Check background task status
    if arxiv_id in _analysis_tasks:
        task_status = _analysis_tasks[arxiv_id]
        if task_status == "processing":
            return AnalyzeResponse(arxiv_id=arxiv_id, status="processing")
        elif task_status.startswith("error:"):
            return AnalyzeResponse(
                arxiv_id=arxiv_id,
                status="error",
                error=task_status[7:],
            )

    return AnalyzeResponse(
        arxiv_id=arxiv_id,
        status=result["status"],
        analysis=result.get("analysis"),
    )


@router.get("/papers/by-date", response_model=PaperListResponse)
async def get_papers_by_date(
    user: AuthUser = Depends(require_auth),
    date: str | None = Query(None, description="Single date query (YYYY-MM-DD)"),
    start_date: str | None = Query(None, description="Range query start date"),
    end_date: str | None = Query(None, description="Range query end date"),
    limit: int = Query(20, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
) -> PaperListResponse:
    """Query papers by date.

    Three query modes:
    1. No params: Returns today's papers (default)
    2. date=YYYY-MM-DD: Returns papers published on that date
    3. start_date + end_date: Returns papers in date range

    Results are sorted by published_at.

    Reason: Simple API design matching RESTful best practices.
    Default to today's papers aligns with user's primary use case.
    """
    # 1. Validate and normalize date parameters
    start_dt, end_dt = _validate_date_params(date, start_date, end_date)

    # 2. Get storage instance
    storage = get_storage()

    # 3. Count total papers
    total = await storage.count_papers_by_date(start_dt, end_dt)

    # 4. Query papers in date range
    papers = await storage.get_papers_by_date(start_dt, end_dt)

    # 5. Sort by published_at
    papers = sorted(
        papers,
        key=lambda p: p.published_at,
        reverse=(sort_order == "desc"),
    )

    # 6. Apply pagination
    paginated_papers = papers[offset : offset + limit]

    # 7. Build response
    return PaperListResponse(
        total=total,
        count=len(paginated_papers),
        limit=limit,
        offset=offset,
        papers=[
            PaperListItemResponse(
                arxiv_id=p.arxiv_id,
                title=p.title,
                title_zh=p.summary.title_zh if p.summary else None,
                abstract=p.abstract,
                abstract_zh=p.summary.abstract_zh if p.summary else None,
                authors=p.authors,
                categories=p.categories,
                published_at=p.published_at,
                abs_url=p.abs_url,
                pdf_url=p.pdf_url,
                has_summary=p.summary is not None,
                has_deep_analysis=(p.summary is not None and p.summary.deep_analysis is not None),
            )
            for p in paginated_papers
        ],
        query_date=date,
        query_range=({"start": start_date, "end": end_date} if start_date and end_date else None),
    )


@router.get("/papers/{arxiv_id}", response_model=PaperResponse)
async def get_paper(arxiv_id: str, user: AuthUser = Depends(require_auth)) -> PaperResponse:
    """Get paper information by arXiv ID.

    Args:
        arxiv_id: arXiv paper ID.

    Returns:
        Paper information.
    """
    storage = get_storage()
    paper = await storage.get_paper_by_arxiv_id(arxiv_id)

    if not paper:
        raise HTTPException(
            status_code=404,
            detail=f"Paper with arXiv ID {arxiv_id} not found",
        )

    return PaperResponse(
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        title_zh=paper.summary.title_zh if paper.summary else None,
        abstract=paper.abstract,
        abstract_zh=paper.summary.abstract_zh if paper.summary else None,
        authors=paper.authors,
        categories=paper.categories,
        abs_url=paper.abs_url,
        pdf_url=paper.pdf_url,
        has_summary=paper.summary is not None,
        has_deep_analysis=(paper.summary is not None and paper.summary.deep_analysis is not None),
    )


def _count_notifier_channels(notifier: Notifier) -> int:
    """Count number of active notification channels.

    Reason: Provides visibility into how many channels received the notification.
    """
    from citeo.notifiers.multi import MultiNotifier

    if isinstance(notifier, MultiNotifier):
        return len(notifier._notifiers)
    return 1


@router.post("/papers/{arxiv_id}/resend", response_model=ResendResponse)
async def resend_paper(
    arxiv_id: str,
    force: bool = Query(False, description="Ignore relevance score threshold"),
    user: AuthUser = Depends(require_auth),
) -> ResendResponse:
    """Resend paper summary notification to all configured channels.

    Sends the paper's AI-generated summary to all configured notification
    channels (Telegram, Feishu, etc.) even if it was already sent before.

    Args:
        arxiv_id: arXiv paper ID (e.g., "2512.14709")
        force: If True, ignore MIN_NOTIFICATION_SCORE threshold
        user: Authenticated user

    Returns:
        ResendResponse with status and notification details

    Raises:
        HTTPException 404: Paper not found
        HTTPException 400: Paper has no summary or score too low
        HTTPException 503: Notification channels not configured
        HTTPException 500: Failed to send notification
    """
    log = logger.bind(arxiv_id=arxiv_id, force=force, user=user.user_id)
    log.info("Resend paper notification requested")

    # 1. Get paper from storage
    storage = get_storage()
    paper = await storage.get_paper_by_arxiv_id(arxiv_id)

    if not paper:
        log.warning("Paper not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper with arXiv ID {arxiv_id} not found",
        )

    # 2. Validate paper has AI summary
    if not paper.summary:
        log.warning("Paper has no AI summary")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Paper {arxiv_id} has no AI summary. "
            f"Use POST /api/papers/{arxiv_id}/analyze to generate summary first.",
        )

    # 3. Check relevance score (unless force=True)
    notifier = get_notifier()
    if not notifier:
        log.error("Notification channels not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notification channels not configured. "
            "Set NOTIFIER_TYPES, TELEGRAM_BOT_TOKEN, etc. in environment.",
        )

    if not force:
        # Get settings to check min_notification_score
        from citeo.config.settings import settings

        min_score = settings.min_notification_score
        if paper.summary.relevance_score < min_score:
            log.warning(
                "Paper score below threshold",
                score=paper.summary.relevance_score,
                threshold=min_score,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Paper relevance score {paper.summary.relevance_score:.1f} "
                f"is below threshold {min_score:.1f}. "
                f"Use force=true to override.",
            )

    # 4. Send notification
    success = await notifier.send_paper(paper)

    if not success:
        log.error("Failed to send notification")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send notification to one or more channels",
        )

    # 5. Count notification channels
    notified_channels = _count_notifier_channels(notifier)

    log.info("Paper notification resent successfully", channels=notified_channels)

    return ResendResponse(
        status="success",
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        notified_channels=notified_channels,
        message="Paper resent successfully",
    )


@router.post("/daily-task/trigger", response_model=TriggerDailyTaskResponse)
async def trigger_daily_task(
    request: Request,
    force: bool = Query(False, description="Force re-notification of already sent papers"),
    user: AuthUser = Depends(require_auth),
) -> TriggerDailyTaskResponse:
    """Manually trigger today's daily task.

    Intelligently handles different scenarios:
    - If no papers fetched today: Runs full pipeline (fetch + process + notify)
    - If papers exist but some unnotified: Processes and notifies pending papers
    - If all papers already notified:
      - force=false: Returns status without re-sending
      - force=true: Resets flags and re-sends notifications

    Args:
        request: FastAPI request object (to access app.state)
        force: If True, re-notify papers already sent today
        user: Authenticated user

    Returns:
        TriggerDailyTaskResponse with execution statistics

    Raises:
        HTTPException 503: Paper service not available
        HTTPException 500: Task trigger failed

    Reason: Provides manual control over daily pipeline execution,
    useful for testing, recovery, or on-demand updates.
    """
    log = logger.bind(endpoint="trigger_daily_task", force=force, user=user.user_id)
    log.info("Daily task trigger requested")

    # Get paper service from app.state
    # Reason: paper_service is stored in app.state during lifespan startup
    paper_service = getattr(request.app.state, "paper_service", None)
    if not paper_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Paper service not available. Ensure API started with scheduler.",
        )

    try:
        stats = await paper_service.trigger_daily_task(force=force)

        # Build human-readable message
        # Reason: Provide clear feedback to user about what happened
        status_messages = {
            "fetched_and_notified": f"Fetched {stats['papers_fetched']} papers, "
            f"notified {stats['papers_notified']} high-score papers",
            "processed_and_notified": f"Processed {stats['papers_processed']} pending papers, "
            f"notified {stats['papers_notified']} papers",
            "re_notified": f"Re-sent {stats['papers_notified']} papers from today",
            "already_notified": f"All {stats['papers_total']} papers already notified. "
            f"Use force=true to re-send.",
        }

        message = status_messages.get(
            stats["status"], f"Task completed with status: {stats['status']}"
        )

        log.info("Daily task completed", **stats)

        return TriggerDailyTaskResponse(
            status=stats["status"],
            papers_total=stats["papers_total"],
            papers_fetched=stats.get("papers_fetched", 0),
            papers_new=stats.get("papers_new", 0),
            papers_processed=stats["papers_processed"],
            papers_notified=stats["papers_notified"],
            message=message,
            errors=stats.get("errors", []),
        )

    except Exception as e:
        log.error("Daily task trigger failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger daily task: {str(e)}",
        )


# Web view rate limiter
# Reason: Protect public view endpoint from DoS attacks
_view_rate_limiter = InMemoryRateLimiter(
    RateLimitConfig(
        requests=100,  # 100 views per window
        window_seconds=60,  # 1 minute window
    )
)


def _validate_arxiv_id(arxiv_id: str) -> bool:
    """Validate arXiv ID format to prevent injection attacks.

    Reason: Input validation for public endpoint without authentication.
    """
    # arXiv ID format: YYMM.NNNNN or YYMM.NNNNNN or archive/YYMMNNN
    pattern = r"^(\d{4}\.\d{4,5}|[a-z\-]+/\d{7})$"
    return bool(re.match(pattern, arxiv_id, re.IGNORECASE))


def _generate_filename(arxiv_id: str) -> str:
    """Generate safe filename for markdown export.

    Reason: arXiv IDs may contain slashes in old format, need sanitization.
    """
    safe_id = arxiv_id.replace("/", "-")
    return f"{safe_id}-analysis.md"


def _generate_markdown_content(paper) -> str:  # type: ignore[no-untyped-def]
    """Generate markdown content for export.

    Creates a well-structured markdown document with Chinese deep analysis
    and English metadata, suitable for blog publishing.

    Args:
        paper: Paper object with summary.deep_analysis populated

    Returns:
        Complete markdown document as string
    """
    # Get summary for convenience
    # Reason: Avoid repetitive None checks in f-string formatting
    summary = paper.summary

    # Format metadata
    authors_str = ", ".join(paper.authors) if paper.authors else "Unknown"
    categories_str = ", ".join(paper.categories) if paper.categories else "Uncategorized"
    published_date = paper.published_at.strftime("%Y-%m-%d")

    # Build markdown document
    # Reason: Use Chinese title as H1 (primary for Chinese blog),
    # English metadata preserves citation accuracy
    markdown_content = f"""# {summary.title_zh}

## {paper.title}

**Authors:** {authors_str}
**Categories:** {categories_str}
**Published:** {published_date}
**arXiv:** [Abstract]({paper.abs_url}) | [PDF]({paper.pdf_url})

## Abstract

{paper.abstract}

**中文摘要：**

{summary.abstract_zh}

---

## Deep Analysis

{summary.deep_analysis}

---

*Generated by Citeo - arXiv RSS subscription with AI summarization*
"""

    return markdown_content


@router.get(
    "/view/{arxiv_id}",
    response_class=HTMLResponse,
    tags=["web-view"],
    summary="View deep analysis in browser",
    description="Returns a beautifully formatted HTML page of the deep analysis report. "
    "Public access, no authentication required. Link can be shared and bookmarked.",
    responses={
        200: {
            "description": "HTML page with formatted analysis",
            "content": {"text/html": {"example": "<!DOCTYPE html>..."}},
        },
        400: {"description": "Invalid arXiv ID format"},
        404: {"description": "Paper not found or analysis not available"},
        429: {"description": "Rate limit exceeded (100 requests/minute per IP)"},
    },
)
async def view_analysis(arxiv_id: str, request: Request) -> HTMLResponse:
    """View deep analysis in web page (public access, no authentication required).

    Provides a beautifully formatted web view of the deep analysis report.
    The link is publicly accessible and can be shared or bookmarked.

    Args:
        arxiv_id: arXiv paper ID (e.g., "2512.14709")
        request: FastAPI request object (required by Jinja2Templates)

    Returns:
        HTMLResponse with rendered analysis page

    Raises:
        HTTPException 429: Rate limit exceeded
        HTTPException 400: Invalid arXiv ID format
        HTTPException 404: Paper not found or analysis not available
    """
    # 1. Rate limit by IP address
    # Reason: Prevent DoS attacks on public endpoint
    client_ip = request.client.host if request.client else "unknown"

    try:
        _view_rate_limiter.check_rate_limit(client_ip)
    except RateLimitExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many requests. Please try again in {e.retry_after} seconds.",
            headers={"Retry-After": str(e.retry_after)},
        )

    # 2. Validate arXiv ID format
    # Reason: Prevent path traversal and injection attacks
    if not _validate_arxiv_id(arxiv_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid arXiv ID format: {arxiv_id}",
        )

    # 3. Fetch paper from storage
    storage = get_storage()
    paper = await storage.get_paper_by_arxiv_id(arxiv_id)

    if not paper:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper with arXiv ID {arxiv_id} not found",
        )

    # 4. Check if deep analysis exists
    if not paper.summary or not paper.summary.deep_analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deep analysis not available for paper {arxiv_id}. "
            "Please trigger analysis first.",
        )

    # 5. Convert Markdown to HTML
    # Reason: Deep analysis is stored in Markdown format, need HTML for web view
    analysis_html = markdown.markdown(
        paper.summary.deep_analysis,
        extensions=[
            "fenced_code",  # ```code blocks```
            "tables",  # | table | support |
            "nl2br",  # Convert \n to <br>
        ],
    )

    # 6. Render template
    return templates.TemplateResponse(
        "analysis_view.html",
        {
            "request": request,
            "paper": paper,
            "analysis_html": analysis_html,
        },
    )


@router.get(
    "/export/{arxiv_id}",
    response_class=PlainTextResponse,
    tags=["web-view"],
    summary="Export deep analysis as Markdown",
    description="Downloads the deep analysis report as a Markdown file.",
    responses={
        200: {"description": "Markdown file download"},
        400: {"description": "Invalid arXiv ID format"},
        404: {"description": "Paper not found or analysis not available"},
        429: {"description": "Rate limit exceeded"},
    },
)
async def export_analysis(arxiv_id: str, request: Request) -> PlainTextResponse:
    """Export deep analysis as downloadable Markdown file.

    Provides the deep analysis as a well-formatted markdown document
    suitable for blog publishing. Includes Chinese deep analysis with
    English metadata.

    Args:
        arxiv_id: arXiv paper ID (e.g., "2512.14709")
        request: FastAPI request object (for rate limiting)

    Returns:
        PlainTextResponse with markdown content and download headers

    Raises:
        HTTPException 429: Rate limit exceeded
        HTTPException 400: Invalid arXiv ID format
        HTTPException 404: Paper not found or analysis not available
    """
    # 1. Rate limit by IP address
    # Reason: Reuse view rate limiter (export typically follows viewing)
    client_ip = request.client.host if request.client else "unknown"

    try:
        _view_rate_limiter.check_rate_limit(client_ip)
    except RateLimitExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many requests. Please try again in {e.retry_after} seconds.",
            headers={"Retry-After": str(e.retry_after)},
        )

    # 2. Validate arXiv ID format
    # Reason: Prevent path traversal and injection attacks
    if not _validate_arxiv_id(arxiv_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid arXiv ID format: {arxiv_id}",
        )

    # 3. Fetch paper from storage
    storage = get_storage()
    paper = await storage.get_paper_by_arxiv_id(arxiv_id)

    if not paper:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper with arXiv ID {arxiv_id} not found",
        )

    # 4. Check if deep analysis exists
    if not paper.summary or not paper.summary.deep_analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deep analysis not available for paper {arxiv_id}",
        )

    # 5. Generate markdown content
    markdown_content = _generate_markdown_content(paper)

    # 6. Generate filename
    filename = _generate_filename(arxiv_id)

    # 7. Return as downloadable file
    # Reason: Content-Disposition triggers browser download,
    # UTF-8 encoding ensures Chinese characters display correctly
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "text/markdown; charset=utf-8",
    }

    return PlainTextResponse(content=markdown_content, headers=headers)
