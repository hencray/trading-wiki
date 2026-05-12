-- Phase 2C v2 — Chart extraction (video scene-change frames).
-- v1 (image-source: PDF/EPUB/Discord) shares the same schema; that workstream
-- is deferred until image-source content is ingested.

CREATE TABLE charts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_content_id INTEGER NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    source_chunk_id INTEGER REFERENCES chunks(id) ON DELETE SET NULL,
    source_timestamp_seconds REAL NOT NULL,
    image_path TEXT NOT NULL,    -- gitignored on-disk frame (storage/charts/<hash>.jpg)
    image_hash TEXT NOT NULL,    -- sha256 of the image bytes — dedup key
    is_chart INTEGER NOT NULL CHECK (is_chart IN (0,1)),
    ticker TEXT,
    timeframe TEXT,
    date_range TEXT,
    indicators TEXT NOT NULL DEFAULT '[]',
    annotations TEXT NOT NULL DEFAULT '[]',
    pattern_description TEXT,
    confidence TEXT NOT NULL CHECK (confidence IN ('low','medium','high')),
    prompt_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(image_hash, prompt_version)
);

CREATE INDEX idx_charts_content ON charts(source_content_id);
CREATE INDEX idx_charts_chunk ON charts(source_chunk_id);
CREATE INDEX idx_charts_ticker ON charts(ticker);
CREATE INDEX idx_charts_is_chart ON charts(is_chart);
