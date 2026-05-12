-- Phase 2A Slice 6c — Rule + MarketCondition entity tables.

CREATE TABLE rules (
    id INTEGER PRIMARY KEY,
    source_chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    statement TEXT NOT NULL,
    rationale TEXT,
    category TEXT NOT NULL CHECK (category IN ('trading','risk','mindset','process')),
    confidence TEXT NOT NULL CHECK (confidence IN ('low','medium','high')),
    prompt_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_rules_chunk ON rules(source_chunk_id);
CREATE INDEX idx_rules_category ON rules(category);

CREATE TABLE market_conditions (
    id INTEGER PRIMARY KEY,
    source_chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    description TEXT NOT NULL,
    time_window TEXT,
    affected_instruments TEXT NOT NULL DEFAULT '[]',
    confidence TEXT NOT NULL CHECK (confidence IN ('low','medium','high')),
    prompt_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_market_conditions_chunk ON market_conditions(source_chunk_id);
CREATE INDEX idx_market_conditions_label ON market_conditions(label);

-- Widen pass2_runs.extractor CHECK to allow 'rule' and 'market_condition'.

CREATE TABLE pass2_runs_new (
    id INTEGER PRIMARY KEY,
    source_chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    extractor TEXT NOT NULL CHECK (extractor IN (
        'trade_example','concept','strategy','setup','rule','market_condition'
    )),
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
