-- Phase 2A Slice 6b — Setup entity table.
-- Setup = preconditions + trigger pattern, usually embedded within a Strategy
-- description. Per-chunk candidates; cross-chunk merge via a future Pass 3
-- reuse slice.

CREATE TABLE setups (
    id INTEGER PRIMARY KEY,
    source_chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    preconditions TEXT NOT NULL,
    trigger TEXT NOT NULL,
    indicators_used TEXT NOT NULL DEFAULT '[]',
    market_conditions TEXT NOT NULL DEFAULT '[]',
    confidence TEXT NOT NULL CHECK (confidence IN ('low','medium','high')),
    prompt_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_setups_chunk ON setups(source_chunk_id);
CREATE INDEX idx_setups_name ON setups(name);

-- Widen pass2_runs.extractor CHECK to allow 'setup'.

CREATE TABLE pass2_runs_new (
    id INTEGER PRIMARY KEY,
    source_chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    extractor TEXT NOT NULL CHECK (extractor IN ('trade_example','concept','strategy','setup')),
    prompt_version TEXT NOT NULL,
    entity_count INTEGER NOT NULL CHECK (entity_count >= 0),
    run_at TEXT NOT NULL,
    UNIQUE(source_chunk_id, extractor, prompt_version)
);

INSERT INTO pass2_runs_new
    (id, source_chunk_id, extractor, prompt_version, entity_count, run_at)
SELECT id, source_chunk_id, extractor, prompt_version, entity_count, run_at
FROM pass2_runs;

DROP TABLE pass2_runs;
ALTER TABLE pass2_runs_new RENAME TO pass2_runs;

CREATE INDEX idx_pass2_runs_chunk ON pass2_runs(source_chunk_id);
