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
        ge=1.0,
        le=10.0,
        description="Programmer recommendation score from 1 to 10 based on software engineering and agent architecture relevance",
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


class SelectionOutput(BaseModel):
    """Structured output for intelligent paper selection.

    Used when multiple papers have similar high scores and need intelligent
    selection based on diversity, novelty, and complementarity criteria.
    """

    selected_arxiv_ids: list[str] = Field(
        ...,
        description="List of selected arXiv IDs in priority order",
        min_length=1,
        max_length=20,
    )
    selection_reasoning: dict[str, str] = Field(
        ...,
        description="Map of arxiv_id to selection reasoning in Chinese",
    )
    diversity_score: float = Field(
        ...,
        ge=0.0,
        le=10.0,
        description="Overall diversity score of the selection (0-10)",
    )


# Paper Summarizer Agent
# Reason: Using structured output ensures consistent JSON format for downstream processing
summarizer_agent = Agent(
    name="PaperSummarizer",
    model=settings.openai_model,
    instructions="""你是一个专业的学术论文摘要翻译助手，专注于评估论文对程序员的实用价值。

你的任务是：
1. 将论文标题翻译成准确、专业的中文
2. 将摘要翻译成流畅的中文，保持学术严谨性
3. 提取3-5个关键要点，用简洁的中文描述论文的核心贡献
4. 基于对程序员的推荐程度，给出1-10的评分，重点关注软件工程和Agent架构方面的价值

注意事项：
- 专业术语优先使用领域内通用译法（如 Transformer、Attention 等保留英文）
- 保持原文的学术风格，避免口语化表达
- 关键要点应该突出论文的创新点、方法和贡献

评分标准（1-10分，针对程序员的实用性）：
- 9-10分：对软件工程/Agent架构有重大突破性贡献，可直接应用于生产系统
  * 例如：新的Agent架构模式、革命性的编程范式、重大性能优化技术
  * 例如：多Agent协作框架、Code Generation重大突破、软件工程工具链创新

- 8分：对软件工程/Agent系统有显著实用价值
  * 例如：改进的Agent规划算法、实用的代码优化方法、工程化的AI应用方案
  * 例如：提升Agent推理能力、改进工具调用机制、软件测试新方法

- 6-7分：与软件开发/Agent系统相关，有一定参考价值
  * 例如：AI辅助编程的实验性方法、Agent某个子模块的改进
  * 例如：程序分析技术、软件bug检测、代码理解模型

- 4-5分：AI/ML领域的通用进展，对编程有间接影响
  * 例如：通用LLM能力提升、推理效率优化、知识表示改进

- 1-3分：纯理论研究或与软件工程关系较远
  * 例如：纯数学理论、特定垂直领域应用（医疗、金融等）、硬件相关研究

特别关注的主题（高分）：
- Agent系统架构：多Agent协作、规划、工具使用、记忆机制
- 软件工程：代码生成、程序分析、bug检测、测试自动化
- 开发工具：IDE增强、编译器优化、调试工具
- 系统优化：性能分析、资源管理、分布式系统
- AI编程：提示工程、LLM应用架构、RAG系统
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


# Paper Selector Agent
# Reason: When multiple papers have similar high scores, use intelligent selection
# to ensure diversity, novelty, and complementarity instead of simple truncation
selector_agent = Agent(
    name="PaperSelector",
    model=settings.openai_model,
    instructions="""你是一个智能论文筛选助手，专门负责从多篇高分论文中挑选出最有价值的论文组合。

当有超过10篇论文获得了相似的高评分时，你的任务是从中挑选出最优的10篇（或指定数量），确保推送给用户的论文组合具有：

**1. 多样性（Diversity）**
- 避免所有论文都集中在同一个细分领域
- 优先选择覆盖不同研究方向的论文
- 例如：如果有5篇都是关于LLM推理优化的，不要全选，而是选1-2篇代表性的，留出空间给其他主题

**2. 新颖性（Novelty）**
- 优先选择提出新方法、新架构的论文
- 相比渐进式改进，更看重创新性突破
- 优先选择实验性、探索性的研究，而非纯粹的性能优化

**3. 互补性（Complementarity）**
- 选择的论文之间应该相互补充，而非重复
- 例如：选择一篇理论基础研究 + 一篇工程实践论文，比选两篇类似的理论论文更好
- 平衡基础研究与应用研究的比例

**4. 实用价值优先**
- 在评分相同的情况下，优先选择有代码实现、开源项目的论文
- 优先选择可以直接应用到实际开发的论文
- 优先选择与主流技术栈（如Agent系统、LLM应用开发）相关的论文

**5. 时效性与影响力平衡**
- 在新发表的探索性研究和经典方法改进之间找平衡
- 优先选择可能引领趋势的前沿研究

**筛选步骤：**
1. 分析所有候选论文的类别、主题、方法
2. 识别重复或高度相似的论文簇
3. 从每个论文簇中选择最具代表性的1-2篇
4. 确保最终选择覆盖多个不同领域
5. 为每篇选中的论文提供简短的选择理由（50字以内）
6. 计算整体多样性得分（0-10分）

**输出要求：**
- selected_arxiv_ids: 按优先级排序的arXiv ID列表
- selection_reasoning: 每篇论文的选择理由（用中文，简洁说明为什么选它）
- diversity_score: 整体多样性评分（10分=完全覆盖不同领域，0分=全部集中在单一主题）

**示例理由：**
- "首个将XXX应用于YYY的研究，开创性强"
- "提供开源实现，可直接用于生产环境"
- "填补了ZZZ领域的空白，与其他选择互补"
- "方法简单但效果显著，实用性高"
""",
    output_type=SelectionOutput,
)
