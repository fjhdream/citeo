# Citeo

[![Docker Build](https://github.com/carota/citeo/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/carota/citeo/actions/workflows/docker-publish.yml)
[![Docker Image](https://ghcr-badge.deta.dev/carota/citeo/latest_tag?trim=major&label=latest)](https://github.com/carota/citeo/pkgs/container/citeo)

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

### 方式一：Docker Compose 部署（推荐）

使用预构建的 Docker 镜像快速部署：

```bash
# 1. 克隆项目
git clone https://github.com/carota/citeo.git
cd citeo

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入必要配置：
# - OPENAI_API_KEY（必填）
# - TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID（如使用Telegram）
# - API_BASE_URL（推荐，用于深度分析链接）
# - SIGNED_URL_SECRET（推荐，32+字符随机字符串）

# 3. 拉取最新镜像并启动
docker-compose pull
docker-compose up -d

# 4. 查看日志
docker-compose logs -f citeo

# 5. 停止服务
docker-compose down
```

访问 `http://localhost:8000/api/health` 检查服务状态。

**📖 详细的 Docker 部署文档：** [docs/DOCKER_DEPLOYMENT.md](docs/DOCKER_DEPLOYMENT.md)

### 方式二：本地开发

#### 1. 安装依赖

```bash
# 使用uv安装（推荐）
uv sync
```

#### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑.env填入必要配置：
# - OPENAI_API_KEY（必填）
# - TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID（如使用Telegram）
# - FEISHU_WEBHOOK_URL（如使用飞书）
```

#### 3. 运行

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

## Docker 部署

### 构建镜像

```bash
# 构建Docker镜像
docker-compose build

# 或使用Docker直接构建
docker build -t citeo:latest .
```

### 配置说明

Docker部署通过 `.env` 文件管理配置。容器会：

- 自动创建并持久化 `data/` 目录（SQLite数据库）
- 在容器内以非root用户运行（安全性）
- 暴露8000端口供API访问
- 包含健康检查确保服务正常运行

### 常用命令

```bash
# 启动服务（后台运行）
docker-compose up -d

# 查看实时日志
docker-compose logs -f

# 重启服务
docker-compose restart

# 停止并删除容器
docker-compose down

# 停止并删除容器及数据卷
docker-compose down -v

# 进入容器Shell
docker-compose exec citeo bash

# 手动触发一次任务
docker-compose exec citeo python -m citeo.main --run-once

# 查看容器状态
docker-compose ps
```

### 资源限制

默认配置中设置了资源限制：
- CPU: 0.5-2核
- 内存: 512M-2G

可在 `docker-compose.yml` 中根据需求调整。

### 环境变量管理

Docker部署支持两种方式配置环境变量：

1. **使用 .env 文件（推荐）**
   ```bash
   cp .env.example .env
   # 编辑 .env
   docker-compose up -d
   ```

2. **直接在 docker-compose.yml 中指定**
   ```yaml
   environment:
     OPENAI_API_KEY: your-key-here
     TELEGRAM_BOT_TOKEN: your-token
   ```

### 健康检查

容器包含健康检查机制，每30秒检查API服务是否正常响应：

```bash
# 查看健康状态
docker-compose ps

# 手动测试健康检查
curl http://localhost:8000/api/health
```

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
