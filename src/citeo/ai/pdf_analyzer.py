"""PDF deep analysis service.

Downloads and analyzes PDF content for in-depth paper analysis.
"""

import tempfile
from pathlib import Path

import httpx
import pymupdf
import structlog
from agents import Runner

from citeo.ai.agents import PDFAnalysisOutput, pdf_analyzer_agent
from citeo.exceptions import AIProcessingError, PDFDownloadError

logger = structlog.get_logger()

# Maximum text length to send to AI (to avoid token limits)
MAX_PDF_TEXT_LENGTH = 500000


async def download_pdf(pdf_url: str, timeout: int = 60) -> bytes:
    """Download PDF from URL.

    Args:
        pdf_url: URL to download PDF from.
        timeout: Request timeout in seconds.

    Returns:
        PDF content as bytes.

    Raises:
        PDFDownloadError: When download fails.
    """
    log = logger.bind(pdf_url=pdf_url)
    log.info("Downloading PDF")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                pdf_url,
                headers={"User-Agent": "Citeo/1.0 (arXiv PDF Analyzer)"},
                follow_redirects=True,
            )
            response.raise_for_status()

            # Verify content type
            content_type = response.headers.get("content-type", "")
            if "pdf" not in content_type.lower():
                log.warning("Unexpected content type", content_type=content_type)

            log.info("PDF downloaded", size_bytes=len(response.content))
            return response.content

    except httpx.TimeoutException as e:
        raise PDFDownloadError(pdf_url, f"Download timed out: {e}") from e
    except httpx.HTTPStatusError as e:
        raise PDFDownloadError(
            pdf_url, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        ) from e
    except httpx.RequestError as e:
        raise PDFDownloadError(pdf_url, f"Request failed: {e}") from e


def extract_text_from_pdf(pdf_content: bytes) -> str:
    """Extract text content from PDF bytes.

    Args:
        pdf_content: PDF file content as bytes.

    Returns:
        Extracted text content.
    """
    # Write to temp file for pymupdf
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_content)
        temp_path = Path(f.name)

    try:
        doc = pymupdf.open(temp_path)
        text_parts = []

        for page in doc:
            text_parts.append(page.get_text())

        doc.close()

        full_text = "\n\n".join(text_parts)

        # Truncate if too long
        if len(full_text) > MAX_PDF_TEXT_LENGTH:
            full_text = full_text[:MAX_PDF_TEXT_LENGTH] + "\n\n[Text truncated due to length...]"

        return full_text

    finally:
        # Clean up temp file
        temp_path.unlink(missing_ok=True)


async def analyze_pdf(arxiv_id: str, pdf_url: str) -> str:
    """Perform deep analysis on a paper's PDF.

    Downloads the PDF, extracts text, and uses AI for in-depth analysis.

    Args:
        arxiv_id: arXiv paper ID for logging.
        pdf_url: URL to the PDF file.

    Returns:
        Formatted analysis text in Chinese.

    Raises:
        PDFDownloadError: When PDF download fails.
        AIProcessingError: When AI analysis fails.
    """
    log = logger.bind(arxiv_id=arxiv_id)
    log.info("Starting PDF analysis")

    # Download PDF
    pdf_content = await download_pdf(pdf_url)

    # Extract text
    log.info("Extracting text from PDF")
    pdf_text = extract_text_from_pdf(pdf_content)
    log.info("Text extracted", text_length=len(pdf_text))

    # Analyze with AI
    prompt = f"""请对以下论文进行深度分析：

论文ID: {arxiv_id}

论文全文:
{pdf_text}
"""

    try:
        result = await Runner.run(pdf_analyzer_agent, prompt)
        output: PDFAnalysisOutput = result.final_output

        # Format analysis as readable text
        analysis = _format_analysis(output)

        log.info("PDF analysis completed")
        return analysis

    except Exception as e:
        log.error("PDF analysis failed", error=str(e))
        raise AIProcessingError(arxiv_id, f"PDF analysis failed: {e}") from e


def _format_analysis(output: PDFAnalysisOutput) -> str:
    """Format analysis output as readable text.

    Reason: Put plain-language explanations first for better readability.
    """
    sections = [
        "## 💡 这篇论文在研究什么？",
        output.methodology_explained,
        "",
        "## 🎯 发现了什么重要的东西？",
        output.key_findings_explained,
        "",
        "## 🌍 对我们有什么影响？",
        output.impact_explained,
        "",
        "## 📋 专业总结",
        "",
        "### 研究方法",
        output.methodology,
        "",
        "### 关键发现",
        *[f"- {finding}" for finding in output.key_findings],
        "",
        "### 局限性",
        *[f"- {limitation}" for limitation in output.limitations],
        "",
        "### 未来工作方向",
        output.future_work,
        "",
        "### 整体评价",
        output.overall_assessment,
    ]

    return "\n".join(sections)
