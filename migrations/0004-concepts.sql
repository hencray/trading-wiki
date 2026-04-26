-- Phase 2A v0.2: Pass 2 (Concept) output table.
-- See docs/superpowers/specs/2026-04-25-phase-2a-pass2-design.md §5.1.

CREATE TABLE concepts (
    id INTEGER PRIMARY KEY,
    source_chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    term TEXT NOT NULL,
    definition TEXT NOT NULL,
    related_terms TEXT NOT NULL DEFAULT '[]',
    confidence TEXT NOT NULL CHECK (confidence IN ('low','medium','high')),
    prompt_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_concepts_chunk ON concepts(source_chunk_id);
CREATE INDEX idx_concepts_term ON concepts(term);
