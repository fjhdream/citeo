"""Admin routes for paper management.

Provides an authenticated HTML page for viewing papers and retrying AI processing.
"""

import re
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from citeo.ai.summarizer import summarize_paper
from citeo.api.routes import get_pdf_service, get_storage
from citeo.auth.dependencies import require_auth
from citeo.auth.models import AuthUser
from citeo.exceptions import AIProcessingError

admin_page_router = APIRouter(tags=["admin"])
admin_api_router = APIRouter(prefix="/api/admin/papers", tags=["admin"])

_templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


def _validate_arxiv_id(arxiv_id: str) -> bool:
    pattern = r"^(\d{4}\.\d{4,5}|[a-z\-]+/\d{7})$"
    return bool(re.match(pattern, arxiv_id, re.IGNORECASE))


def _get_fetched_day_range(date_str: str | None) -> tuple[datetime, datetime]:
    day = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.utcnow()
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


@admin_page_router.get("/admin/papers", response_class=HTMLResponse)
async def admin_papers_page(
    request: Request,
    user: AuthUser = Depends(require_auth),
    date: str | None = Query(None),
) -> HTMLResponse:
    start_dt, end_dt = _get_fetched_day_range(date)
    papers = await get_storage().get_papers_by_fetched_date(start_dt, end_dt)
    papers = sorted(papers, key=lambda paper: paper.published_at, reverse=True)

    return templates.TemplateResponse(
        "admin_papers.html",
        {
            "request": request,
            "papers": papers,
            "selected_date": start_dt.strftime("%Y-%m-%d"),
            "api_key": request.query_params.get("api_key", ""),
            "stats": {
                "total": len(papers),
                "with_summary": sum(1 for paper in papers if paper.summary),
                "with_analysis": sum(
                    1
                    for paper in papers
                    if paper.summary and paper.summary.deep_analysis
                ),
            },
        },
    )


@admin_api_router.post("/{arxiv_id}/retry-summary")
async def retry_summary(
    arxiv_id: str,
    user: AuthUser = Depends(require_auth),
) -> dict[str, str]:
    if not _validate_arxiv_id(arxiv_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid arXiv ID format: {arxiv_id}",
        )

    storage = get_storage()
    paper = await storage.get_paper_by_arxiv_id(arxiv_id)
    if not paper:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper with arXiv ID {arxiv_id} not found",
        )

    try:
        summary = await summarize_paper(paper)
        await storage.update_summary(paper.guid, summary)
    except AIProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return {
        "status": "success",
        "arxiv_id": arxiv_id,
        "message": "Summary regenerated",
    }


@admin_api_router.post("/{arxiv_id}/retry-analysis")
async def retry_analysis(
    arxiv_id: str,
    user: AuthUser = Depends(require_auth),
) -> dict[str, str]:
    if not _validate_arxiv_id(arxiv_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid arXiv ID format: {arxiv_id}",
        )

    storage = get_storage()
    paper = await storage.get_paper_by_arxiv_id(arxiv_id)
    if not paper:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Paper with arXiv ID {arxiv_id} not found",
        )

    result = await get_pdf_service().analyze_paper(
        arxiv_id,
        force=True,
        skip_notification=True,
    )

    if result["status"] == "error":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["error"],
        )

    return {
        "status": "success",
        "arxiv_id": arxiv_id,
        "message": "Deep analysis regenerated",
    }
