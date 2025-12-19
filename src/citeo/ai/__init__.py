"""AI processing package."""

from citeo.ai.agents import (
    PDFAnalysisOutput,
    SummaryOutput,
    pdf_analyzer_agent,
    summarizer_agent,
)
from citeo.ai.pdf_analyzer import analyze_pdf
from citeo.ai.summarizer import summarize_paper, summarize_papers

__all__ = [
    "summarizer_agent",
    "pdf_analyzer_agent",
    "SummaryOutput",
    "PDFAnalysisOutput",
    "summarize_paper",
    "summarize_papers",
    "analyze_pdf",
]
