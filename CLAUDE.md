# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

```bash
# Install dependencies
uv sync

# Start API server with scheduler (daily job at 8:00)
uv run citeo

# Run pipeline once immediately
uv run citeo --run-once

# Fetch-only mode (no AI/notifications)
uv run python scripts/run_daily.py --fetch-only

# Linting
uv run ruff check .
uv run ruff format .

# Type checking
uv run mypy src/

# Run tests
uv run pytest
uv run pytest tests/test_file.py::test_function  # single test
```

## Architecture

**Data Flow:**
```
RSS Feed → sources/ → parsers/ → storage/ (dedup) → ai/ (translate) → notifiers/
                                       ↑
                              API triggers PDF analysis
```

**Key Layers:**
- `sources/` - RSS fetching with `FeedSource` Protocol
- `parsers/` - XML parsing with `FeedParser` Protocol
- `storage/` - SQLite persistence with `PaperStorage` Protocol
- `ai/` - OpenAI Agents SDK for summarization/translation
- `notifiers/` - Telegram push with `Notifier` Protocol
- `services/paper_service.py` - Main orchestrator (Facade pattern)
- `api/routes.py` - FastAPI endpoints for PDF analysis triggers

**Core Models:**
- `Paper` - arXiv paper with computed `pdf_url` property
- `PaperSummary` - AI-generated Chinese translation and key points

**Configuration:**
- All config via `config/settings.py` using pydantic-settings
- Environment variables from `.env` file
- Required: `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

## Code Conventions

- Use Protocol for interfaces (not ABC)
- Async throughout (httpx, aiosqlite, python-telegram-bot)
- structlog for logging
- Add `# Reason:` comments for non-obvious design decisions
