# Citeo

arXiv RSS订阅 + AI摘要翻译 + Telegram推送系统

## 功能

- 每日定时拉取arXiv RSS（默认cs.AI分类）
- 使用AI（GPT-4o）进行论文摘要翻译成中文
- 通过Telegram逐篇推送论文更新
- 支持通过API触发PDF深度分析

## 快速开始

### 1. 安装依赖

```bash
# 使用uv安装
uv sync
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑.env填入：
# - OPENAI_API_KEY
# - TELEGRAM_BOT_TOKEN
# - TELEGRAM_CHAT_ID
```

### 3. 运行

```bash
# 启动API服务器（带定时任务）
uv run citeo

# 或手动执行一次
uv run citeo --run-once

# 仅抓取不发送（测试用）
uv run python scripts/run_daily.py --fetch-only
```

## API端点

- `GET /api/health` - 健康检查
- `GET /api/papers/{arxiv_id}` - 获取论文信息
- `POST /api/papers/{arxiv_id}/analyze` - 触发PDF分析
- `GET /api/papers/{arxiv_id}/analysis` - 获取分析结果

## 项目结构

```
citeo/
├── config/settings.py      # 配置管理
├── src/citeo/
│   ├── models/             # 数据模型
│   ├── sources/            # RSS源
│   ├── parsers/            # 解析器
│   ├── ai/                 # AI处理
│   ├── storage/            # 存储层
│   ├── notifiers/          # 通知推送
│   ├── services/           # 业务服务
│   ├── api/                # API层
│   ├── scheduler.py        # 调度器
│   └── main.py             # 入口
└── scripts/                # 工具脚本
```

## 配置

主要配置项（通过环境变量）：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| OPENAI_API_KEY | OpenAI API密钥 | 必填 |
| OPENAI_MODEL | AI模型 | gpt-4o |
| TELEGRAM_BOT_TOKEN | Telegram Bot令牌 | 必填 |
| TELEGRAM_CHAT_ID | 目标聊天ID | 必填 |
| DAILY_FETCH_HOUR | 每日执行小时 | 8 |
| DAILY_FETCH_MINUTE | 每日执行分钟 | 0 |
| DB_PATH | 数据库路径 | data/citeo.db |

## License

MIT
