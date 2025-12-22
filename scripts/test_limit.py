#!/usr/bin/env python
"""Test script to verify daily notification limit feature.

This script tests the max_daily_notifications setting with mock data.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from citeo.models.paper import Paper, PaperSummary


def create_mock_papers(count: int) -> list[Paper]:
    """Create mock papers with high scores for testing.

    Args:
        count: Number of papers to create.

    Returns:
        List of mock papers with scores >= 8.0.
    """
    papers = []
    for i in range(count):
        score = 9.0 - (i * 0.1)  # Scores: 9.0, 8.9, 8.8, ...
        if score < 8.0:
            score = 8.0 + (i % 10) * 0.05  # Keep above 8.0

        from datetime import datetime, timezone

        paper = Paper(
            guid=f"test-{i:03d}",
            arxiv_id=f"2312.{i:05d}",
            title=f"Test Paper {i+1}: Advanced AI Research Topic {chr(65 + i % 26)}",
            abstract=f"This is a test paper about advanced AI topic {i+1}. " * 10,
            authors=[f"Author {i+1}", f"Author {i+2}"],
            categories=[f"cs.AI", f"cs.LG"],
            abs_url=f"https://arxiv.org/abs/2312.{i:05d}",
            published_at=datetime(2023, 12, (i % 28) + 1, 0, 0, 0, tzinfo=timezone.utc),
            source_id="test",
        )

        # Add summary with score
        paper.summary = PaperSummary(
            title_zh=f"测试论文 {i+1}",
            abstract_zh=f"这是一篇关于高级AI主题{i+1}的测试论文。",
            key_points=[
                f"要点 1: 关于主题{i+1}的发现",
                f"要点 2: 新的方法论",
                f"要点 3: 实验结果",
            ],
            relevance_score=score,
        )

        papers.append(paper)

    return papers


async def test_notification_limit():
    """Test notification limit logic."""
    from citeo.config.settings import settings

    print("=== 每日推送论文数量限制功能测试 ===\n")

    # Test 1: Few papers (< limit)
    print("测试 1: 少于限制 (5篇高分论文)")
    print(f"配置限制: {settings.max_daily_notifications} 篇")
    papers = create_mock_papers(5)
    print(f"高分论文数: {len(papers)}")

    # Simulate filtering logic
    max_limit = settings.max_daily_notifications
    total = len(papers)
    if max_limit and len(papers) > max_limit:
        papers_to_send = papers[:max_limit]
        truncated = True
    else:
        papers_to_send = papers
        truncated = False

    print(f"实际推送: {len(papers_to_send)} 篇")
    print(
        f"是否截断: {'是 (' + str(total - len(papers_to_send)) + '篇被过滤)' if truncated else '否'}"
    )
    print(f"Telegram标题: ", end="")
    if truncated:
        print(f"今日新论文: {len(papers_to_send)}/{total} 篇 (已按评分筛选)")
    else:
        print(f"今日新论文: {len(papers_to_send)} 篇")
    print()

    # Test 2: Exactly at limit
    print("测试 2: 正好等于限制 (10篇高分论文)")
    papers = create_mock_papers(10)
    print(f"高分论文数: {len(papers)}")

    total = len(papers)
    if max_limit and len(papers) > max_limit:
        papers_to_send = papers[:max_limit]
        truncated = True
    else:
        papers_to_send = papers
        truncated = False

    print(f"实际推送: {len(papers_to_send)} 篇")
    print(
        f"是否截断: {'是 (' + str(total - len(papers_to_send)) + '篇被过滤)' if truncated else '否'}"
    )
    print(f"Telegram标题: ", end="")
    if truncated:
        print(f"今日新论文: {len(papers_to_send)}/{total} 篇 (已按评分筛选)")
    else:
        print(f"今日新论文: {len(papers_to_send)} 篇")
    print()

    # Test 3: Over limit
    print("测试 3: 超过限制 (25篇高分论文)")
    papers = create_mock_papers(25)
    print(f"高分论文数: {len(papers)}")

    total = len(papers)
    if max_limit and len(papers) > max_limit:
        papers_to_send = papers[:max_limit]
        truncated = True
    else:
        papers_to_send = papers
        truncated = False

    print(f"实际推送: {len(papers_to_send)} 篇")
    print(
        f"是否截断: {'是 (' + str(total - len(papers_to_send)) + '篇被过滤)' if truncated else '否'}"
    )
    print(f"Telegram标题: ", end="")
    if truncated:
        print(f"今日新论文: {len(papers_to_send)}/{total} 篇 (已按评分筛选)")
    else:
        print(f"今日新论文: {len(papers_to_send)} 篇")
    print()

    # Test 4: Show selected papers
    print("测试 4: 显示被选中的论文 (前3篇)")
    for i, paper in enumerate(papers_to_send[:3], 1):
        score = paper.summary.relevance_score if paper.summary else 0
        print(f"  {i}. [{paper.arxiv_id}] {paper.title[:50]}... (评分: {score:.1f})")
    print(f"  ... 还有 {len(papers_to_send) - 3} 篇\n")

    print("✅ 测试完成!")
    print(f"\n配置说明:")
    print(f"- 当前限制: {settings.max_daily_notifications} 篇/天")
    print(f"- 修改限制: 在 .env 文件中设置 MAX_DAILY_NOTIFICATIONS=5")
    print(f"- 禁用限制: 在 .env 文件中设置 MAX_DAILY_NOTIFICATIONS= (留空)")


if __name__ == "__main__":
    asyncio.run(test_notification_limit())
