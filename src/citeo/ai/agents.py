"""OpenAI Agents configuration and definitions.

Defines agents for paper summarization and translation using OpenAI Agents SDK.
"""

from agents import Agent, set_default_openai_client, set_tracing_disabled
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

# Import settings and configure OpenAI client
# Reason: Must be done at module load time before agents are created
from citeo.config.settings import settings

_client = AsyncOpenAI(
    api_key=settings.openai_api_key.get_secret_value(),
    base_url=settings.openai_base_url,
    timeout=settings.openai_timeout,
)
set_default_openai_client(_client)

# Configure tracing
# Reason: Tracing requires a valid OpenAI API key. When using custom base URL,
# tracing needs a separate key or should be disabled to avoid 401 errors.
if not settings.openai_tracing_enabled:
    set_tracing_disabled(True)
elif settings.openai_tracing_api_key:
    # Reason: Use separate tracing client with official OpenAI endpoint
    from agents import set_tracing_export_api_key

    set_tracing_export_api_key(settings.openai_tracing_api_key.get_secret_value())
elif settings.openai_base_url:
    # Reason: Using custom base URL without tracing key will cause 401 errors
    # Auto-disable tracing to prevent errors
    set_tracing_disabled(True)


class SummaryOutput(BaseModel):
    """Structured output for paper summarization.

    Used as output_type for the summarizer agent to ensure consistent response format.
    """

    title_zh: str = Field(..., description="Chinese translated title")
    abstract_zh: str = Field(..., description="Chinese translated abstract")
    key_points: list[str] = Field(
        ...,
        description="3-5 key points in Chinese highlighting main contributions",
    )
    relevance_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Relevance score from 0 to 1 based on innovation and impact",
    )


class PDFAnalysisOutput(BaseModel):
    """Structured output for PDF deep analysis."""

    methodology: str = Field(..., description="Research methodology summary in Chinese")
    methodology_explained: str = Field(
        ..., description="Plain language explanation of methodology for non-experts"
    )
    key_findings: list[str] = Field(..., description="Key findings in Chinese")
    key_findings_explained: str = Field(
        ..., description="Plain language explanation of why findings matter"
    )
    limitations: list[str] = Field(..., description="Limitations noted in Chinese")
    future_work: str = Field(..., description="Future work suggestions in Chinese")
    overall_assessment: str = Field(..., description="Overall assessment in Chinese")
    impact_explained: str = Field(
        ...,
        description="Plain language explanation of real-world impact and significance",
    )


# Paper Summarizer Agent
# Reason: Using structured output ensures consistent JSON format for downstream processing
summarizer_agent = Agent(
    name="PaperSummarizer",
    model=settings.openai_model,
    instructions="""你是一个专业的学术论文摘要翻译助手。

你的任务是：
1. 将论文标题翻译成准确、专业的中文
2. 将摘要翻译成流畅的中文，保持学术严谨性
3. 提取3-5个关键要点，用简洁的中文描述论文的核心贡献
4. 根据AI/ML领域的热度、创新性和潜在影响力，给出0-1的相关性评分

注意事项：
- 专业术语优先使用领域内通用译法（如 Transformer、Attention 等保留英文）
- 保持原文的学术风格，避免口语化表达
- 关键要点应该突出论文的创新点、方法和贡献
- 评分标准：0.8-1.0 突破性/高影响力，0.5-0.8 有价值的改进，0.3-0.5 增量式贡献，0-0.3 一般性工作
""",
    output_type=SummaryOutput,
)


# PDF Deep Analysis Agent
pdf_analyzer_agent = Agent(
    name="PDFAnalyzer",
    model=settings.openai_model,
    instructions="""你是一个专业的学术论文深度分析助手，擅长将复杂的学术内容转化为普通人也能理解的语言。

你将收到论文的完整内容（从PDF提取的文本）。请进行深度分析，包括：

1. **研究方法 (methodology)**：
   - 用专业语言总结论文使用的研究方法论
   - 【重要】然后用大白话解释 (methodology_explained)：就像在给一个聪明但不懂技术的朋友解释，用生活中的例子或类比来说明这个方法是怎么工作的

2. **关键发现 (key_findings)**：
   - 列出3-5个最重要的研究发现（专业表述）
   - 【重要】然后用大白话解释这些发现为什么重要 (key_findings_explained)：解释这些发现解决了什么问题，为什么值得关注，对实际应用有什么帮助

3. **局限性 (limitations)**：
   - 指出论文中提到的或你观察到的局限性
   - 用通俗的语言说明这些局限性意味着什么

4. **未来工作 (future_work)**：
   - 总结论文提出的未来研究方向
   - 用简单的语言解释为什么这些方向值得探索

5. **整体评价 (overall_assessment)**：
   - 给出对这篇论文的专业评价

6. **影响力解读 (impact_explained)**：
   - 【重要】用大白话解释这篇论文的现实意义：如果这个研究成功了，会对我们的生活、工作或者这个领域产生什么影响？普通人为什么应该关心这个研究？

写作风格要求：
- 专业术语部分：保持学术严谨性，保留英文原词并附上中文解释
- 大白话解释部分：像跟朋友聊天一样，用生活化的例子、比喻和场景来解释
- 避免"该研究表明"、"本文提出"等学术八股文，用"简单来说"、"打个比方"、"这就像..."等表达
- 把复杂概念拆解成普通人能理解的小块，用"首先...然后...最后..."的逻辑链条
""",
    output_type=PDFAnalysisOutput,
)
