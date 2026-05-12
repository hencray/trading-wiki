-- Phase 2A Pass 4 — Relationship Building.
-- Generic triples (subject, predicate, object) across all entity types.
-- Subject/object reference per-type entity tables by (entity_type, entity_id);
-- the FK is not declared at the DB level because SQLite can't express
-- polymorphic FKs. Application code validates references.

CREATE TABLE entity_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_type TEXT NOT NULL CHECK (subject_type IN (
        'trade_example','concept','strategy','setup','rule','market_condition'
    )),
    subject_id INTEGER NOT NULL,
    predicate TEXT NOT NULL CHECK (predicate IN (
        'uses','prerequisite_for','variant_of','contradicts','supports',
        'depends_on','illustrates','applies_in'
    )),
    object_type TEXT NOT NULL CHECK (object_type IN (
        'trade_example','concept','strategy','setup','rule','market_condition'
    )),
    object_id INTEGER NOT NULL,
    source_chunk_id INTEGER REFERENCES chunks(id) ON DELETE SET NULL,
    confidence TEXT NOT NULL CHECK (confidence IN ('low','medium','high')),
    rationale TEXT,
    prompt_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(subject_type, subject_id, predicate, object_type, object_id, prompt_version)
);

CREATE INDEX idx_entity_relationships_subject
    ON entity_relationships(subject_type, subject_id);
CREATE INDEX idx_entity_relationships_object
    ON entity_relationships(object_type, object_id);
CREATE INDEX idx_entity_relationships_chunk
    ON entity_relationships(source_chunk_id);

-- Track Pass 4 runs per chunk (mirrors pass2_runs).

CREATE TABLE pass4_runs (
    id INTEGER PRIMARY KEY,
    source_chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    prompt_version TEXT NOT NULL,
    relationship_count INTEGER NOT NULL CHECK (relationship_count >= 0),
    run_at TEXT NOT NULL,
    UNIQUE(source_chunk_id, prompt_version)
);

CREATE INDEX idx_pass4_runs_chunk ON pass4_runs(source_chunk_id);
