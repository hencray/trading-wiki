-- Phase 2A Pass 3 — Concept entity resolution.
-- Records the verdict (and supporting evidence) for each Concept row about
-- whether it canonicalizes to another Concept row. The vec0 virtual table
-- ``concept_embeddings`` that stores per-concept embedding vectors is created
-- lazily at runtime by the resolver (vec0 requires the sqlite-vec extension
-- to be loaded; SQL migrations don't load extensions). Keeping the
-- canonical-rollup metadata in a regular SQL table here means downstream
-- queries don't depend on the extension.

CREATE TABLE concept_resolutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_id INTEGER NOT NULL REFERENCES concepts(id),
    canonical_concept_id INTEGER NOT NULL REFERENCES concepts(id),
    similarity_score REAL,
    llm_verdict TEXT NOT NULL CHECK (llm_verdict IN ('same','different','unclear')),
    llm_reason TEXT,
    embedding_model TEXT NOT NULL,
    embedding_model_version TEXT NOT NULL,
    resolved_at TEXT NOT NULL,
    UNIQUE(concept_id, embedding_model_version)
);

CREATE INDEX idx_concept_resolutions_canonical
    ON concept_resolutions(canonical_concept_id);
