-- Phase 2B — Review queue.
-- Auto-populated from entities/relationships matching trigger criteria.
-- Reviewed in the Streamlit review UI (Phase 2B follow-up).

CREATE TABLE review_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_kind TEXT NOT NULL CHECK (target_kind IN ('entity','relationship')),
    entity_type TEXT,
    entity_id INTEGER,
    relationship_id INTEGER REFERENCES entity_relationships(id) ON DELETE CASCADE,
    trigger TEXT NOT NULL CHECK (trigger IN (
        'low_confidence_entity',
        'contradicts_relationship',
        'codeability_4plus',
        'borderline_merge'
    )),
    severity TEXT NOT NULL CHECK (severity IN ('low','medium','high')),
    is_hard_gate INTEGER NOT NULL DEFAULT 0 CHECK (is_hard_gate IN (0,1)),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','accepted','rejected','edited','skipped')),
    notes TEXT,
    queued_at TEXT NOT NULL,
    resolved_at TEXT,
    -- Reject malformed rows: entity items need (entity_type, entity_id); rel items need relationship_id.
    CHECK (
        (target_kind = 'entity' AND entity_type IS NOT NULL AND entity_id IS NOT NULL
            AND relationship_id IS NULL)
        OR
        (target_kind = 'relationship' AND relationship_id IS NOT NULL
            AND entity_type IS NULL AND entity_id IS NULL)
    )
);

CREATE INDEX idx_review_queue_status ON review_queue(status);
CREATE INDEX idx_review_queue_trigger ON review_queue(trigger);
CREATE INDEX idx_review_queue_entity ON review_queue(entity_type, entity_id);
CREATE INDEX idx_review_queue_hard_gate ON review_queue(is_hard_gate, status);
