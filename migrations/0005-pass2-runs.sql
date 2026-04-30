-- Phase 2A v0.3: Pass 2 idempotency tracking.
-- Records that an extractor ran on a chunk at a prompt_version, with the
-- entity_count that was written. Distinguishes "ran with 0 entities" from
-- "never ran" — the prior idempotency check (entity rows exist) could not.

CREATE TABLE pass2_runs (
    id INTEGER PRIMARY KEY,
    source_chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    extractor TEXT NOT NULL CHECK (extractor IN ('trade_example','concept')),
    prompt_version TEXT NOT NULL,
    entity_count INTEGER NOT NULL CHECK (entity_count >= 0),
    run_at TEXT NOT NULL,
    UNIQUE(source_chunk_id, extractor, prompt_version)
);

CREATE INDEX idx_pass2_runs_chunk ON pass2_runs(source_chunk_id);

-- Backfill from existing entity rows so previously-processed chunks are not
-- re-called on the next batch run. Chunks where the LLM was called and
-- produced zero entities cannot be reconstructed (no rows to read from);
-- those will be re-called once before the new mechanism takes hold.
INSERT INTO pass2_runs (source_chunk_id, extractor, prompt_version, entity_count, run_at)
SELECT
    source_chunk_id,
    'trade_example' AS extractor,
    prompt_version,
    COUNT(*) AS entity_count,
    MAX(created_at) AS run_at
FROM trade_examples
GROUP BY source_chunk_id, prompt_version;

INSERT INTO pass2_runs (source_chunk_id, extractor, prompt_version, entity_count, run_at)
SELECT
    source_chunk_id,
    'concept' AS extractor,
    prompt_version,
    COUNT(*) AS entity_count,
    MAX(created_at) AS run_at
FROM concepts
GROUP BY source_chunk_id, prompt_version;
