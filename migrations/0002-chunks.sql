-- Phase 2A v0.1: Pass 1 (chunk + classify) output table.

CREATE TABLE chunks (
    id INTEGER PRIMARY KEY,
    content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    start_seg_seq INTEGER NOT NULL,
    end_seg_seq INTEGER NOT NULL,
    start_seconds REAL,
    end_seconds REAL,
    label TEXT NOT NULL CHECK (label IN (
        'strategy','concept','example','psychology',
        'market_commentary','qa','noise'
    )),
    confidence TEXT NOT NULL CHECK (confidence IN ('low','medium','high')),
    summary TEXT NOT NULL,
    text TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(content_id, prompt_version, seq)
);

CREATE INDEX idx_chunks_content_id ON chunks(content_id);
CREATE INDEX idx_chunks_label ON chunks(label);
