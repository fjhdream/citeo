"""Intelligent paper selection service.

Uses AI agent to select the most valuable papers when multiple papers
have similar high scores, ensuring diversity, novelty, and complementarity.
"""

import structlog
from agents import Runner

from citeo.ai.agents import SelectionOutput, selector_agent
from citeo.models.paper import Paper

logger = structlog.get_logger()


async def select_papers(
    papers: list[Paper],
    max_count: int = 10,
) -> list[Paper]:
    """Intelligently select top papers from a list of high-scoring papers.

    When there are more high-scoring papers than the limit, use AI agent
    to select the most diverse and valuable combination instead of simple
    truncation.

    Args:
        papers: List of papers to select from (should already be filtered by score).
        max_count: Maximum number of papers to select.

    Returns:
        Selected papers in priority order.

    Reason: Using AI selection ensures diversity and avoids overwhelming users
    with papers on the same narrow topic. The agent considers novelty,
    complementarity, and practical value beyond just the relevance_score.
    """
    if not papers:
        return []

    # If papers count is within limit, no need for intelligent selection
    if len(papers) <= max_count:
        return papers

    log = logger.bind(
        total_papers=len(papers),
        max_count=max_count,
    )
    log.info("Starting intelligent paper selection")

    # Build prompt with paper metadata
    prompt = _build_selection_prompt(papers, max_count)

    try:
        # Run selector agent
        result = await Runner.run(selector_agent, prompt)
        output: SelectionOutput = result.final_output

        log.info(
            "Paper selection completed",
            selected_count=len(output.selected_arxiv_ids),
            diversity_score=output.diversity_score,
        )

        # Reorder papers according to agent's selection
        selected_papers = _reorder_papers(papers, output)

        # Log selection reasoning for observability
        for paper in selected_papers:
            reason = output.selection_reasoning.get(paper.arxiv_id, "未提供理由")
            logger.debug(
                "Paper selected",
                arxiv_id=paper.arxiv_id,
                title=paper.title[:50],
                score=paper.summary.relevance_score if paper.summary else 0,
                reason=reason,
            )

        return selected_papers

    except Exception as e:
        log.error("Intelligent selection failed, falling back to simple truncation", error=str(e))
        # Fallback: simple truncation if AI selection fails
        return papers[:max_count]


def _build_selection_prompt(papers: list[Paper], max_count: int) -> str:
    """Build prompt for selector agent with paper metadata.

    Reason: Include all relevant information for intelligent decision-making:
    arxiv_id, title, abstract, categories, score, and key points.
    """
    papers_info = []

    for i, paper in enumerate(papers, 1):
        summary = paper.summary
        score = summary.relevance_score if summary else 0
        categories = ", ".join(paper.categories[:3])

        # Build paper info block
        info_parts = [
            f"**论文 {i}: {paper.arxiv_id}**",
            f"- 标题: {paper.title}",
            f"- 类别: {categories}",
            f"- 评分: {score:.1f}/10",
        ]

        # Add Chinese translation if available
        if summary and summary.title_zh:
            info_parts.append(f"- 中文标题: {summary.title_zh}")

        # Add abstract (truncated)
        if summary and summary.abstract_zh:
            abstract = (
                summary.abstract_zh[:200] + "..."
                if len(summary.abstract_zh) > 200
                else summary.abstract_zh
            )
            info_parts.append(f"- 摘要: {abstract}")
        else:
            abstract = paper.abstract[:200] + "..." if len(paper.abstract) > 200 else paper.abstract
            info_parts.append(f"- 摘要: {abstract}")

        # Add key points if available
        if summary and summary.key_points:
            key_points_str = "\n  ".join(f"• {p}" for p in summary.key_points[:3])
            info_parts.append(f"- 要点:\n  {key_points_str}")

        papers_info.append("\n".join(info_parts))

    prompt = f"""请从以下 {len(papers)} 篇高分论文中，挑选出最有价值的 {max_count} 篇。

所有论文都已经过初步筛选，评分均在8分以上。你的任务是确保最终推送的论文组合具有多样性、新颖性和互补性。

# 候选论文列表

{chr(10).join(papers_info)}

# 任务要求

请从上述论文中挑选 {max_count} 篇，确保：
1. 覆盖不同的研究方向和主题
2. 优先选择创新性、开创性的研究
3. 避免选择高度相似或重复的论文
4. 平衡理论研究与工程实践
5. 为每篇选中的论文提供简短的选择理由（50字以内）

请按优先级从高到低排序你的选择。
"""

    return prompt


def _reorder_papers(papers: list[Paper], output: SelectionOutput) -> list[Paper]:
    """Reorder papers according to agent's selection.

    Reason: Maintain the priority order specified by the agent, and only
    return the papers that were actually selected.
    """
    # Create a map from arxiv_id to paper
    paper_map = {p.arxiv_id: p for p in papers}

    # Reorder based on agent's selection
    selected_papers = []
    for arxiv_id in output.selected_arxiv_ids:
        if arxiv_id in paper_map:
            selected_papers.append(paper_map[arxiv_id])
        else:
            logger.warning(
                "Agent selected unknown paper",
                arxiv_id=arxiv_id,
                available_ids=[p.arxiv_id for p in papers],
            )

    # If agent didn't return enough papers, fill with remaining ones
    if len(selected_papers) < len(output.selected_arxiv_ids):
        selected_ids = set(output.selected_arxiv_ids)
        for paper in papers:
            if paper.arxiv_id not in selected_ids:
                selected_papers.append(paper)
            if len(selected_papers) >= len(output.selected_arxiv_ids):
                break

    return selected_papers
