-- Phase 1 initial schema: content + segments.
-- See ARCHITECTURE.md for the full module map and PROJECT_PLAN.md §Phase 1
-- for the field rationale.

CREATE TABLE content (
    id INTEGER PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    author TEXT,
    parent_id TEXT,
    created_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    UNIQUE(source_type, source_id)
);

CREATE INDEX idx_content_source_type ON content(source_type);
CREATE INDEX idx_content_parent_id ON content(parent_id);

CREATE TABLE segments (
    id INTEGER PRIMARY KEY,
    content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    text TEXT NOT NULL,
    start_seconds REAL,
    end_seconds REAL,
    embedding_id INTEGER,
    UNIQUE(content_id, seq)
);

CREATE INDEX idx_segments_content_id ON segments(content_id);
