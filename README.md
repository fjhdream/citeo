# Citeo

arXiv RSS订阅 + AI摘要翻译 + 多渠道推送系统

## 功能特性

- 每日定时拉取arXiv RSS（支持多个分类订阅）
- 使用OpenAI Agents SDK进行论文摘要翻译成中文
- 提取关键要点和相关性评分
- 支持多渠道推送（Telegram、飞书）
- 支持通过API触发PDF深度分析
- 并行AI处理，支持可配置并发限制
- 支持SQLite和Cloudflare D1双存储后端

## 快速开始

### 1. 安装依赖

```bash
# 使用uv安装（推荐）
uv sync
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑.env填入必要配置：
# - OPENAI_API_KEY（必填）
# - TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID（如使用Telegram）
# - FEISHU_WEBHOOK_URL（如使用飞书）
```

### 3. 运行

```bash
# 启动API服务器（带定时任务调度器）
uv run citeo

# 立即执行一次完整流程
uv run citeo --run-once

# 仅抓取保存，不进行AI处理和推送（测试用）
uv run python scripts/run_daily.py --fetch-only
```

## API端点

- `GET /api/health` - 健康检查
- `GET /api/papers` - 获取论文列表（支持分页和过滤）
- `GET /api/papers/{arxiv_id}` - 获取单篇论文信息
- `POST /api/papers/{arxiv_id}/analyze` - 触发PDF深度分析
- `GET /api/papers/{arxiv_id}/analysis` - 获取深度分析结果
- `POST /api/trigger` - 手动触发完整流程

## 项目结构

```
citeo/
├── src/citeo/
│   ├── models/             # 数据模型 (Paper, PaperSummary)
│   ├── sources/            # RSS源适配器 (ArxivFeedSource)
│   ├── parsers/            # XML解析器 (ArxivParser)
│   ├── ai/                 # AI处理 (OpenAI Agents SDK)
│   ├── storage/            # 存储层 (SQLite, Cloudflare D1)
│   ├── notifiers/          # 通知推送 (Telegram, 飞书, 多渠道)
│   ├── services/           # 业务服务编排 (PaperService)
│   ├── api/                # FastAPI路由
│   ├── config/             # 配置管理 (pydantic-settings)
│   ├── scheduler.py        # APScheduler定时任务
│   └── main.py             # 应用入口
├── scripts/                # 工具脚本
│   └── run_daily.py        # 手动执行脚本
└── tests/                  # 测试文件
```

## 配置说明

主要配置项（通过环境变量）：

### OpenAI配置
| 变量 | 说明 | 默认值 |
|------|------|--------|
| OPENAI_API_KEY | OpenAI API密钥 | 必填 |
| OPENAI_MODEL | AI模型 | gpt-4o |
| OPENAI_BASE_URL | 自定义API端点（兼容OpenAI的API） | 可选 |
| OPENAI_TIMEOUT | API超时时间（秒） | 60 |
| OPENAI_TRACING_ENABLED | 是否启用Agents SDK追踪 | true |
| AI_MAX_CONCURRENT | 并行AI处理的最大并发数 | 5 |

### 通知渠道配置
| 变量 | 说明 | 默认值 |
|------|------|--------|
| NOTIFIER_TYPES | 通知渠道列表（逗号分隔） | ["telegram"] |
| TELEGRAM_BOT_TOKEN | Telegram Bot令牌 | 使用Telegram时必填 |
| TELEGRAM_CHAT_ID | Telegram目标聊天ID | 使用Telegram时必填 |
| FEISHU_WEBHOOK_URL | 飞书机器人Webhook地址 | 使用飞书时必填 |
| FEISHU_SECRET | 飞书Webhook签名密钥 | 可选 |

### 数据库配置
| 变量 | 说明 | 默认值 |
|------|------|--------|
| DB_TYPE | 数据库类型 (sqlite/d1) | sqlite |
| DB_PATH | SQLite数据库文件路径 | data/citeo.db |
| D1_ACCOUNT_ID | Cloudflare账户ID | DB_TYPE=d1时必填 |
| D1_DATABASE_ID | D1数据库ID | DB_TYPE=d1时必填 |
| D1_API_TOKEN | Cloudflare API令牌 | DB_TYPE=d1时必填 |

### 调度配置
| 变量 | 说明 | 默认值 |
|------|------|--------|
| DAILY_FETCH_HOUR | 每日执行小时（0-23） | 8 |
| DAILY_FETCH_MINUTE | 每日执行分钟（0-59） | 0 |

### RSS订阅配置
| 变量 | 说明 | 默认值 |
|------|------|--------|
| FEED_URLS | RSS订阅URL列表（JSON数组） | ["https://rss.arxiv.org/rss/cs.AI"] |
| RSS_FETCH_TIMEOUT | RSS获取超时（秒） | 30 |

### AI处理配置
| 变量 | 说明 | 默认值 |
|------|------|--------|
| ENABLE_TRANSLATION | 是否启用AI翻译 | true |
| ENABLE_DEEP_ANALYSIS | 是否启用深度分析 | false |
| MAX_PAPERS_PER_BATCH | 单次处理论文上限 | 50 |

### API服务配置
| 变量 | 说明 | 默认值 |
|------|------|--------|
| API_HOST | API服务监听地址 | 0.0.0.0 |
| API_PORT | API服务端口 | 8000 |

## 架构设计

### 数据流
```
RSS订阅源 → 解析器 → 存储去重 → AI翻译（并行） → 多渠道推送
                                    ↑
                            API触发深度分析
```

### 核心设计模式
- **Protocol协议**: 所有核心接口使用Protocol定义（非ABC），实现灵活的鸭子类型
- **Facade外观模式**: PaperService作为业务编排层
- **异步优先**: 全异步架构（httpx, aiosqlite, python-telegram-bot异步版）
- **并发控制**: 使用asyncio.Semaphore限制并发，防止API限流

### 性能优化
- AI处理采用并行化设计，默认最多5个并发任务
- 如有10篇论文需处理（每篇3秒），从串行30秒优化到并行6秒
- 通过`AI_MAX_CONCURRENT`可调节并发数，平衡速度与API限额

## 开发

### 代码检查
```bash
# 格式化
uv run ruff format .

# 代码检查
uv run ruff check .

# 类型检查（需安装mypy）
uv run mypy src/
```

### 测试
```bash
uv run pytest
uv run pytest tests/test_file.py::test_function  # 单个测试
```

## License

MIT
