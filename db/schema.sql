-- RepeaterMock PRO Scraper — D1 Schema (NEW database)
DROP TABLE IF EXISTS tests;
DROP TABLE IF EXISTS test_inventory;
DROP TABLE IF EXISTS series;
DROP TABLE IF EXISTS runs;
DROP TABLE IF EXISTS refresh_log;

CREATE TABLE series (
    platform TEXT NOT NULL DEFAULT 'tb-pro',
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    series_url TEXT NOT NULL UNIQUE,
    series_id_remote TEXT,
    total_tests INTEGER DEFAULT 0,
    scraped_count INTEGER DEFAULT 0,
    partial_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    pending_count INTEGER DEFAULT 0,
    last_fetched_at INTEGER,
    last_scraped_at INTEGER,
    created_at INTEGER DEFAULT (unixepoch()),
    updated_at INTEGER DEFAULT (unixepoch()),
    PRIMARY KEY (platform, slug)
);

CREATE TABLE test_inventory (
    test_id TEXT PRIMARY KEY,
    series_slug TEXT NOT NULL,
    series_name TEXT,
    title TEXT,
    section TEXT,
    subsection TEXT,
    duration_minutes INTEGER,
    total_marks INTEGER,
    question_count INTEGER,
    discovered_at INTEGER DEFAULT (unixepoch())
);
CREATE INDEX idx_inv_series ON test_inventory(series_slug);

CREATE TABLE tests (
    test_id TEXT PRIMARY KEY,
    series_slug TEXT NOT NULL,
    title TEXT,
    section TEXT,
    subsection TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    has_questions INTEGER DEFAULT 0,
    has_answers INTEGER DEFAULT 0,
    has_solutions INTEGER DEFAULT 0,
    has_analysis INTEGER DEFAULT 0,
    actual_questions INTEGER DEFAULT 0,
    error_message TEXT,
    last_attempted_at INTEGER,
    scraped_at INTEGER,
    file_path TEXT,
    file_size_bytes INTEGER,
    created_at INTEGER DEFAULT (unixepoch()),
    updated_at INTEGER DEFAULT (unixepoch())
);
CREATE INDEX idx_tests_status ON tests(status);
CREATE INDEX idx_tests_series ON tests(series_slug);

CREATE TABLE runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at INTEGER NOT NULL,
    ended_at INTEGER,
    time_minutes REAL,
    tests_scraped INTEGER DEFAULT 0,
    tests_partial INTEGER DEFAULT 0,
    tests_failed INTEGER DEFAULT 0,
    questions_scraped INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',
    notes TEXT
);

CREATE TABLE refresh_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    trigger TEXT,
    refresh_status INTEGER,
    new_access_token INTEGER,
    new_refresh_token INTEGER,
    tests_since_last INTEGER,
    notes TEXT
);
