"""API routes for Citeo.

Provides REST API endpoints for PDF analysis and paper queries.
"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from citeo.services.pdf_service import PDFService
from citeo.storage.sqlite import SQLitePaperStorage

router = APIRouter(prefix="/api", tags=["papers"])

# Service instances (will be initialized on app startup)
_storage: Optional[SQLitePaperStorage] = None
_pdf_service: Optional[PDFService] = None


def init_services(db_path: Path) -> None:
    """Initialize API services.

    Must be called before API routes can be used.

    Args:
        db_path: Path to SQLite database.
    """
    global _storage, _pdf_service
    _storage = SQLitePaperStorage(db_path)
    _pdf_service = PDFService(_storage)


def get_pdf_service() -> PDFService:
    """Get PDF service instance."""
    if _pdf_service is None:
        raise RuntimeError("Services not initialized. Call init_services first.")
    return _pdf_service


def get_storage() -> SQLitePaperStorage:
    """Get storage instance."""
    if _storage is None:
        raise RuntimeError("Services not initialized. Call init_services first.")
    return _storage


# Request/Response models


class AnalyzeRequest(BaseModel):
    """Request to analyze a paper's PDF."""

    arxiv_id: str = Field(..., description="arXiv paper ID (e.g., 2512.14709)")


class AnalyzeResponse(BaseModel):
    """Response from PDF analysis."""

    arxiv_id: str
    status: str = Field(..., description="Status: completed, cached, processing, error")
    analysis: Optional[str] = Field(default=None, description="Analysis content")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class PaperResponse(BaseModel):
    """Paper information response."""

    arxiv_id: str
    title: str
    title_zh: Optional[str] = None
    abstract: str
    abstract_zh: Optional[str] = None
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


# Background task storage
_analysis_tasks: dict[str, str] = {}  # arxiv_id -> status


async def _run_analysis_background(arxiv_id: str) -> None:
    """Run PDF analysis in background."""
    _analysis_tasks[arxiv_id] = "processing"
    try:
        result = await get_pdf_service().analyze_paper(arxiv_id)
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
) -> AnalyzeResponse:
    """Trigger PDF deep analysis for a paper.

    Args:
        arxiv_id: arXiv paper ID.
        sync: If True, wait for analysis to complete. Otherwise run in background.

    Returns:
        Analysis result or processing status.
    """
    pdf_service = get_pdf_service()

    if sync:
        # Synchronous mode: wait for completion
        try:
            result = await pdf_service.analyze_paper(arxiv_id)
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

        # Check if already processing
        if arxiv_id in _analysis_tasks and _analysis_tasks[arxiv_id] == "processing":
            return AnalyzeResponse(
                arxiv_id=arxiv_id,
                status="processing",
            )

        # Start background task
        background_tasks.add_task(_run_analysis_background, arxiv_id)

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
        has_deep_analysis=(
            paper.summary is not None and paper.summary.deep_analysis is not None
        ),
    )
