-- Phase 2A Slice 6 — Strategy entity table. Per-chunk extraction; Pass 3
-- entity-resolution (cross-chunk merge into canonical Strategy entities)
-- is a separate slice that reuses the resolver pattern from Pass 3 Concept
-- MVP. Each row here is a Strategy *candidate* drawn from one chunk; until
-- Pass 3 runs, the same underlying Strategy may have multiple candidate
-- rows from different chunks.

CREATE TABLE strategies (
    id INTEGER PRIMARY KEY,
    source_chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    thesis TEXT NOT NULL,
    entry_rules TEXT NOT NULL,
    exit_rules TEXT NOT NULL,
    risk_management TEXT,
    indicators_used TEXT NOT NULL DEFAULT '[]',
    timeframe TEXT,
    instruments TEXT NOT NULL DEFAULT '[]',
    codeability_score INTEGER,
    confidence TEXT NOT NULL CHECK (confidence IN ('low','medium','high')),
    prompt_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK (codeability_score IS NULL
           OR (codeability_score BETWEEN 1 AND 5))
);

CREATE INDEX idx_strategies_chunk ON strategies(source_chunk_id);
CREATE INDEX idx_strategies_name ON strategies(name);
