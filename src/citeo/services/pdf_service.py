"""PDF analysis service.

Handles on-demand PDF deep analysis requests.
"""

import structlog

from citeo.ai.pdf_analyzer import analyze_pdf
from citeo.exceptions import AIProcessingError, PDFDownloadError
from citeo.notifiers.base import Notifier
from citeo.storage.base import PaperStorage

logger = structlog.get_logger()


class PDFService:
    """PDF analysis service.

    Handles API-triggered deep analysis of paper PDFs.
    """

    def __init__(self, storage: PaperStorage, notifier: Notifier | None = None):
        """Initialize PDF service.

        Args:
            storage: Paper storage instance.
            notifier: Optional notifier for sending analysis results.
        """
        self._storage = storage
        self._notifier = notifier

    async def analyze_paper(self, arxiv_id: str, force: bool = False) -> dict:
        """Analyze a paper's PDF by arXiv ID.

        Args:
            arxiv_id: arXiv paper ID (e.g., "2512.14709").
            force: If True, force re-analysis even if cached result exists.

        Returns:
            dict: Analysis result with status and content.

        Raises:
            ValueError: If paper not found in database.
        """
        log = logger.bind(arxiv_id=arxiv_id, force=force)
        log.info("PDF analysis requested")

        # Get paper from storage
        paper = await self._storage.get_paper_by_arxiv_id(arxiv_id)
        if not paper:
            log.warning("Paper not found")
            raise ValueError(f"Paper with arXiv ID {arxiv_id} not found in database")

        # Check if already analyzed (skip if force=True)
        if not force and paper.summary and paper.summary.deep_analysis:
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

            # Send notification if notifier is configured
            # Reason: Fetch updated paper from storage to ensure we have the latest data
            if self._notifier:
                updated_paper = await self._storage.get_paper_by_arxiv_id(arxiv_id)
                if updated_paper and updated_paper.summary and updated_paper.summary.deep_analysis:
                    try:
                        await self._notifier.send_deep_analysis(updated_paper)
                        log.info("Deep analysis notification sent")
                    except Exception as e:
                        log.warning("Failed to send deep analysis notification", error=str(e))

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
