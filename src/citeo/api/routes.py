"""API routes for Citeo.

Provides REST API endpoints for PDF analysis and paper queries.
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from citeo.config.settings import Settings
from citeo.notifiers.base import Notifier
from citeo.notifiers.factory import create_notifier
from citeo.services.pdf_service import PDFService
from citeo.storage import PaperStorage, create_storage

router = APIRouter(prefix="/api", tags=["papers"])

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
            )
    except ValueError as e:
        # Log warning but don't fail initialization
        import structlog

        logger = structlog.get_logger()
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


# Background task storage
_analysis_tasks: dict[str, str] = {}  # arxiv_id -> status


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


# Routes


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok", version="0.1.0")


@router.post("/papers/{arxiv_id}/analyze", response_model=AnalyzeResponse)
async def analyze_paper(
    arxiv_id: str,
    background_tasks: BackgroundTasks,
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
async def get_analysis(arxiv_id: str) -> AnalyzeResponse:
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
async def get_paper(arxiv_id: str) -> PaperResponse:
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
