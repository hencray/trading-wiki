-- Phase 2A v0.2: Pass 2 (TradeExample) output table.

CREATE TABLE trade_examples (
    id INTEGER PRIMARY KEY,
    source_chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('long','short')),
    instrument_type TEXT NOT NULL CHECK (
        instrument_type IN ('stock','option','future','crypto','other')
    ),
    trade_date TEXT,
    entry_price REAL,
    stop_price REAL,
    target_price REAL,
    exit_price REAL,
    entry_description TEXT NOT NULL,
    exit_description TEXT NOT NULL,
    outcome_text TEXT NOT NULL,
    outcome_classification TEXT CHECK (
        outcome_classification IS NULL OR
        outcome_classification IN ('won','lost','scratch','unknown')
    ),
    lessons TEXT,
    confidence TEXT NOT NULL CHECK (confidence IN ('low','medium','high')),
    prompt_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_trade_examples_chunk ON trade_examples(source_chunk_id);
CREATE INDEX idx_trade_examples_ticker ON trade_examples(ticker);
CREATE INDEX idx_trade_examples_outcome ON trade_examples(outcome_classification);
