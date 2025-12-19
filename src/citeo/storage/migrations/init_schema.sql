-- Citeo database schema
-- SQLite compatible

-- Papers table: stores arXiv papers with AI summaries
CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Core identifiers
    guid TEXT UNIQUE NOT NULL,          -- arXiv unique identifier (oai:arXiv.org:...)
    arxiv_id TEXT NOT NULL,             -- arXiv ID (e.g., 2512.14709)

    -- Paper content
    title TEXT NOT NULL,
    abstract TEXT NOT NULL,
    authors TEXT NOT NULL,              -- JSON array of author names
    categories TEXT NOT NULL,           -- JSON array of categories
    announce_type TEXT NOT NULL,        -- new/cross/replace
    published_at TIMESTAMP NOT NULL,

    -- URLs
    abs_url TEXT NOT NULL,

    -- Source metadata
    source_id TEXT NOT NULL,            -- e.g., arxiv.cs.AI
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- AI-generated content
    title_zh TEXT,                      -- Chinese translated title
    abstract_zh TEXT,                   -- Chinese translated abstract
    key_points TEXT,                    -- JSON array of key points
    relevance_score REAL DEFAULT 1.0,   -- Programmer recommendation score (1-10)
    ai_processed_at TIMESTAMP,

    -- PDF deep analysis
    deep_analysis TEXT,
    deep_analysis_at TIMESTAMP,

    -- Notification status
    is_notified INTEGER DEFAULT 0,
    notified_at TIMESTAMP,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_papers_guid ON papers(guid);
CREATE INDEX IF NOT EXISTS idx_papers_arxiv_id ON papers(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_papers_source_id ON papers(source_id);
CREATE INDEX IF NOT EXISTS idx_papers_published_at ON papers(published_at);
CREATE INDEX IF NOT EXISTS idx_papers_is_notified ON papers(is_notified);
CREATE INDEX IF NOT EXISTS idx_papers_fetched_at ON papers(fetched_at);

-- Feed configs table (optional, for database-driven config)
CREATE TABLE IF NOT EXISTS feed_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    parser_type TEXT DEFAULT 'arxiv',
    enabled INTEGER DEFAULT 1,
    config_json TEXT,                   -- Additional config as JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Execution logs for monitoring
CREATE TABLE IF NOT EXISTS execution_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    job_type TEXT NOT NULL,             -- daily_fetch, pdf_analysis, etc.
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    status TEXT NOT NULL,               -- running/success/failed
    papers_fetched INTEGER DEFAULT 0,
    papers_new INTEGER DEFAULT 0,
    papers_notified INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_execution_logs_job_type ON execution_logs(job_type);
CREATE INDEX IF NOT EXISTS idx_execution_logs_status ON execution_logs(status);
CREATE INDEX IF NOT EXISTS idx_execution_logs_started_at ON execution_logs(started_at);
