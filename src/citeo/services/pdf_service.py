"""PDF analysis service.

Handles on-demand PDF deep analysis requests.
"""

import structlog

from citeo.ai.pdf_analyzer import analyze_pdf
from citeo.exceptions import AIProcessingError, PDFDownloadError
from citeo.models.paper import Paper
from citeo.storage.sqlite import SQLitePaperStorage

logger = structlog.get_logger()


class PDFService:
    """PDF analysis service.

    Handles API-triggered deep analysis of paper PDFs.
    """

    def __init__(self, storage: SQLitePaperStorage):
        """Initialize PDF service.

        Args:
            storage: Paper storage instance.
        """
        self._storage = storage

    async def analyze_paper(self, arxiv_id: str) -> dict:
        """Analyze a paper's PDF by arXiv ID.

        Args:
            arxiv_id: arXiv paper ID (e.g., "2512.14709").

        Returns:
            dict: Analysis result with status and content.

        Raises:
            ValueError: If paper not found in database.
        """
        log = logger.bind(arxiv_id=arxiv_id)
        log.info("PDF analysis requested")

        # Get paper from storage
        paper = await self._storage.get_paper_by_arxiv_id(arxiv_id)
        if not paper:
            log.warning("Paper not found")
            raise ValueError(f"Paper with arXiv ID {arxiv_id} not found in database")

        # Check if already analyzed
        if paper.summary and paper.summary.deep_analysis:
            log.info("Returning cached analysis")
            return {
                "arxiv_id": arxiv_id,
                "status": "cached",
                "analysis": paper.summary.deep_analysis,
            }

        # Perform analysis
        try:
            analysis = await analyze_pdf(arxiv_id, paper.pdf_url)

            # Save to storage
            await self._storage.update_deep_analysis(paper.guid, analysis)

            log.info("PDF analysis completed")
            return {
                "arxiv_id": arxiv_id,
                "status": "completed",
                "analysis": analysis,
            }

        except PDFDownloadError as e:
            log.error("PDF download failed", error=str(e))
            return {
                "arxiv_id": arxiv_id,
                "status": "error",
                "error": f"PDF download failed: {e}",
            }

        except AIProcessingError as e:
            log.error("AI analysis failed", error=str(e))
            return {
                "arxiv_id": arxiv_id,
                "status": "error",
                "error": f"AI analysis failed: {e}",
            }

    async def get_analysis(self, arxiv_id: str) -> dict | None:
        """Get existing analysis for a paper.

        Args:
            arxiv_id: arXiv paper ID.

        Returns:
            dict with analysis if exists, None otherwise.
        """
        paper = await self._storage.get_paper_by_arxiv_id(arxiv_id)
        if not paper:
            return None

        if paper.summary and paper.summary.deep_analysis:
            return {
                "arxiv_id": arxiv_id,
                "status": "completed",
                "analysis": paper.summary.deep_analysis,
            }

        return {
            "arxiv_id": arxiv_id,
            "status": "not_analyzed",
            "analysis": None,
        }
