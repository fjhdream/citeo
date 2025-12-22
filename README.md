# Citeo

[![Docker Build](https://github.com/fjhdream/citeo/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/fjhdream/citeo/actions/workflows/docker-publish.yml)
[![Docker Image](https://ghcr-badge.egpl.dev/fjhdream/citeo/latest_tag?trim=major&label=latest)](https://github.com/fjhdream/citeo/pkgs/container/citeo)

[English](README.md) | [简体中文](README.zh.md)

arXiv RSS subscriptions + AI abstract translation + multi-channel notifications

## Features

- Scheduled daily arXiv RSS fetches (multiple categories supported)
- Translate abstracts to Chinese with OpenAI Agents SDK
- Extract key points and relevance scores
- Multi-channel notifications (Telegram, Feishu)
- Trigger PDF deep analysis via API
- Parallel AI processing with configurable concurrency
- Dual storage backends: SQLite and Cloudflare D1

## Quick Start

### Option 1: Docker Compose (recommended)

Deploy quickly with the prebuilt Docker image:

```bash
# 1. Clone the repo
git clone https://github.com/fjhdream/citeo.git
cd citeo

# 2. Configure environment variables
cp .env.example .env
# Edit .env with required values:
# - OPENAI_API_KEY (required)
# - TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (if using Telegram)
# - API_BASE_URL (recommended, for deep analysis links)
# - SIGNED_URL_SECRET (recommended, 32+ random chars)

# 3. Pull latest image and start
docker-compose pull
docker-compose up -d

# 4. View logs
docker-compose logs -f citeo

# 5. Stop
docker-compose down
```

Visit `http://localhost:8000/api/health` to check service status.

**📖 Full Docker deployment docs:** [docs/DOCKER_DEPLOYMENT.md](docs/DOCKER_DEPLOYMENT.md)

### Option 2: Local development

#### 1. Install dependencies

```bash
# Install with uv (recommended)
uv sync
```

#### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env with required values:
# - OPENAI_API_KEY (required)
# - TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (if using Telegram)
# - FEISHU_WEBHOOK_URL (if using Feishu)
```

#### 3. Run

```bash
# Start the API server (with scheduler)
uv run citeo

# Run a full flow immediately
uv run citeo --run-once

# Fetch only, no AI processing or notifications (for testing)
uv run python scripts/run_daily.py --fetch-only
```

## API Endpoints

- `GET /api/health` - Health check
- `GET /api/papers` - List papers (pagination and filters supported)
- `GET /api/papers/{arxiv_id}` - Get a single paper
- `POST /api/papers/{arxiv_id}/analyze` - Trigger PDF deep analysis
- `GET /api/papers/{arxiv_id}/analysis` - Fetch deep analysis results
- `POST /api/trigger` - Manually trigger a full flow

## Project Structure

```
citeo/
├── src/citeo/
│   ├── models/             # Data models (Paper, PaperSummary)
│   ├── sources/            # RSS sources (ArxivFeedSource)
│   ├── parsers/            # XML parsers (ArxivParser)
│   ├── ai/                 # AI processing (OpenAI Agents SDK)
│   ├── storage/            # Storage (SQLite, Cloudflare D1)
│   ├── notifiers/          # Notifications (Telegram, Feishu, etc.)
│   ├── services/           # Business orchestration (PaperService)
│   ├── api/                # FastAPI routes
│   ├── config/             # Configuration (pydantic-settings)
│   ├── scheduler.py        # APScheduler jobs
│   └── main.py             # App entrypoint
├── scripts/                # Utility scripts
│   └── run_daily.py        # Manual run script
└── tests/                  # Tests
```

## Configuration

Primary settings (via environment variables):

### OpenAI
| Variable | Description | Default |
|------|------|--------|
| OPENAI_API_KEY | OpenAI API key | required |
| OPENAI_MODEL | AI model | gpt-4o |
| OPENAI_BASE_URL | Custom API endpoint (OpenAI-compatible) | optional |
| OPENAI_TIMEOUT | API timeout (seconds) | 60 |
| OPENAI_TRACING_ENABLED | Enable Agents SDK tracing | true |
| AI_MAX_CONCURRENT | Max concurrent AI tasks | 5 |

### Notifications
| Variable | Description | Default |
|------|------|--------|
| NOTIFIER_TYPES | Notifier list (comma-separated) | ["telegram"] |
| TELEGRAM_BOT_TOKEN | Telegram bot token | required for Telegram |
| TELEGRAM_CHAT_ID | Telegram chat ID | required for Telegram |
| FEISHU_WEBHOOK_URL | Feishu bot webhook URL | required for Feishu |
| FEISHU_SECRET | Feishu webhook signing secret | optional |

### Database
| Variable | Description | Default |
|------|------|--------|
| DB_TYPE | Database type (sqlite/d1) | sqlite |
| DB_PATH | SQLite database path | data/citeo.db |
| D1_ACCOUNT_ID | Cloudflare account ID | required when DB_TYPE=d1 |
| D1_DATABASE_ID | D1 database ID | required when DB_TYPE=d1 |
| D1_API_TOKEN | Cloudflare API token | required when DB_TYPE=d1 |

### Scheduler
| Variable | Description | Default |
|------|------|--------|
| DAILY_FETCH_HOUR | Daily run hour (0-23) | 8 |
| DAILY_FETCH_MINUTE | Daily run minute (0-59) | 0 |

### RSS
| Variable | Description | Default |
|------|------|--------|
| FEED_URLS | RSS feed URLs (JSON array) | ["https://rss.arxiv.org/rss/cs.AI"] |
| RSS_FETCH_TIMEOUT | RSS fetch timeout (seconds) | 30 |

### AI Processing
| Variable | Description | Default |
|------|------|--------|
| ENABLE_TRANSLATION | Enable AI translation | true |
| ENABLE_DEEP_ANALYSIS | Enable deep analysis | false |
| MAX_PAPERS_PER_BATCH | Max papers per batch | 50 |

### API Service
| Variable | Description | Default |
|------|------|--------|
| API_HOST | API host | 0.0.0.0 |
| API_PORT | API port | 8000 |

## Architecture

### Data Flow
```
RSS feeds → parser → dedupe storage → AI translation (parallel) → multi-channel notifications
                                         ↑
                                 API-triggered deep analysis
```

### Core Design Patterns
- **Protocol interfaces**: core contracts defined with Protocol (not ABC) for duck typing
- **Facade pattern**: PaperService orchestrates the workflow
- **Async-first**: fully async stack (httpx, aiosqlite, async python-telegram-bot)
- **Concurrency control**: asyncio.Semaphore limits concurrency to avoid rate limits

### Performance
- Parallel AI processing, up to 5 concurrent tasks by default
- Example: 10 papers at 3 seconds each drops from 30s serial to ~6s parallel
- Tune concurrency with `AI_MAX_CONCURRENT` to balance speed and API limits

## Docker Deployment

### Build Images

```bash
# Build with Docker Compose
docker-compose build

# Or build directly with Docker
docker build -t citeo:latest .
```

### Configuration Notes

Docker deployment uses the `.env` file. The container will:

- Create and persist the `data/` directory (SQLite database)
- Run as non-root inside the container (security)
- Expose port 8000 for API access
- Include health checks to ensure service availability

### Common Commands

```bash
# Start (detached)
docker-compose up -d

# Tail logs
docker-compose logs -f

# Restart
docker-compose restart

# Stop and remove containers
docker-compose down

# Stop and remove containers + volumes
docker-compose down -v

# Enter container shell
docker-compose exec citeo bash

# Trigger a run manually
docker-compose exec citeo python -m citeo.main --run-once

# Check container status
docker-compose ps
```

### Resource Limits

Default limits in the config:
- CPU: 0.5-2 cores
- Memory: 512M-2G

Adjust in `docker-compose.yml` as needed.

### Environment Variable Management

Docker supports two ways to set environment variables:

1. **Use the .env file (recommended)**
   ```bash
   cp .env.example .env
   # Edit .env
   docker-compose up -d
   ```

2. **Set directly in docker-compose.yml**
   ```yaml
   environment:
     OPENAI_API_KEY: your-key-here
     TELEGRAM_BOT_TOKEN: your-token
   ```

### Health Check

The container has a health check that hits the API every 30 seconds:

```bash
# View health status
docker-compose ps

# Manual check
curl http://localhost:8000/api/health
```

## Development

### Code Quality
```bash
# Format
uv run ruff format .

# Lint
uv run ruff check .

# Type check (requires mypy)
uv run mypy src/
```

### Tests
```bash
uv run pytest
uv run pytest tests/test_file.py::test_function  # single test
```

## License

MIT
