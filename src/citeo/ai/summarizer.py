"""Paper summarization and translation service using OpenAI Agents."""

import structlog
from agents import Runner

from citeo.ai.agents import SummaryOutput, summarizer_agent
from citeo.exceptions import AIProcessingError
from citeo.models.paper import Paper, PaperSummary

logger = structlog.get_logger()


async def summarize_paper(paper: Paper) -> PaperSummary:
    """Generate AI summary and translation for a paper.

    Uses OpenAI Agents SDK to:
    1. Translate title to Chinese
    2. Translate abstract to Chinese
    3. Extract key points
    4. Calculate relevance score

    Args:
        paper: The paper to summarize.

    Returns:
        PaperSummary with translated content and insights.

    Raises:
        AIProcessingError: When AI processing fails.
    """
    log = logger.bind(arxiv_id=paper.arxiv_id, guid=paper.guid)
    log.info("Starting paper summarization")

    prompt = f"""请分析以下arXiv论文：

标题: {paper.title}

摘要: {paper.abstract}

分类: {', '.join(paper.categories)}

作者: {', '.join(paper.authors)}
"""

    try:
        result = await Runner.run(summarizer_agent, prompt)
        output: SummaryOutput = result.final_output

        summary = PaperSummary(
            title_zh=output.title_zh,
            abstract_zh=output.abstract_zh,
            key_points=output.key_points,
            relevance_score=output.relevance_score,
        )

        log.info(
            "Paper summarization completed",
            relevance_score=output.relevance_score,
            key_points_count=len(output.key_points),
        )

        return summary

    except Exception as e:
        log.error("Paper summarization failed", error=str(e))
        raise AIProcessingError(paper.guid, str(e)) from e


async def summarize_papers(papers: list[Paper]) -> list[tuple[Paper, PaperSummary | None]]:
    """Summarize multiple papers, handling failures gracefully.

    Args:
        papers: List of papers to summarize.

    Returns:
        List of (paper, summary) tuples. Summary is None if processing failed.
    """
    results: list[tuple[Paper, PaperSummary | None]] = []

    for paper in papers:
        try:
            summary = await summarize_paper(paper)
            results.append((paper, summary))
        except AIProcessingError as e:
            logger.warning(
                "Skipping paper due to AI error",
                arxiv_id=paper.arxiv_id,
                error=str(e),
            )
            results.append((paper, None))

    return results
