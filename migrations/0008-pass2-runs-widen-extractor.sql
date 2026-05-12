-- Phase 2A Slice 6 — Widen pass2_runs.extractor CHECK to allow 'strategy'.
-- SQLite has no ALTER for CHECK constraints, so we rebuild the table.

CREATE TABLE pass2_runs_new (
    id INTEGER PRIMARY KEY,
    source_chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    extractor TEXT NOT NULL CHECK (extractor IN ('trade_example','concept','strategy')),
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
