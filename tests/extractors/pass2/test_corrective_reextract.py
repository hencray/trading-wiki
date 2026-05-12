"""Tests for the Phase 2A v0.3 corrective slice driver."""

from __future__ import annotations

import sqlite3
from datetime import UTC
from datetime import datetime as _dt
from pathlib import Path


def _seed_baseline_corpus(db_path: Path) -> list[int]:
    """Seed a minimal DB with three chunks: two routed to TradeExample with v1
    TE rows (one of which also has a v2 row from a prior partial re-extract),
    and one routed to qa with no TE rows. Returns the chunk_ids that should be
    discovered as baseline candidates."""
    from trading_wiki.config import (
        PROMPT_VERSION_PASS1,
        PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
        PROMPT_VERSION_PASS2_TRADE_EXAMPLE_V2,
    )
    from trading_wiki.core.db import apply_migrations, save_content_record
    from trading_wiki.handlers.base import ContentRecord, Segment

    apply_migrations(db_path)
    cid = save_content_record(
        db_path,
        ContentRecord(
            source_type="local_video",
            source_id="vid:fixture",
            title="fixture",
            raw_text="t",
            created_at=_dt(2026, 5, 11, tzinfo=UTC),
            ingested_at=_dt(2026, 5, 11, tzinfo=UTC),
            segments=[Segment(seq=0, text="hi", start_seconds=0.0, end_seconds=1.0)],
        ),
    )
    with sqlite3.connect(db_path) as conn:
        for seq, label in enumerate(("example", "example", "qa")):
            conn.execute(
                """
                INSERT INTO chunks
                (content_id, seq, start_seg_seq, end_seg_seq, label, confidence,
                 summary, text, prompt_version, created_at)
                VALUES (?, ?, 0, 0, ?, 'high', 's', 'text', ?, '2026-05-11')
                """,
                (cid, seq, label, PROMPT_VERSION_PASS1),
            )
        chunk_ids = [int(r[0]) for r in conn.execute("SELECT id FROM chunks ORDER BY id")]
        # Chunk 0: 1 v1 TE row (baseline candidate)
        # Chunk 1: 1 v1 + 1 v2 TE row (baseline candidate — v1 row still present)
        # Chunk 2: routed to qa, no TE rows (NOT a baseline candidate)
        for chunk_id, version in (
            (chunk_ids[0], PROMPT_VERSION_PASS2_TRADE_EXAMPLE),
            (chunk_ids[1], PROMPT_VERSION_PASS2_TRADE_EXAMPLE),
            (chunk_ids[1], PROMPT_VERSION_PASS2_TRADE_EXAMPLE_V2),
        ):
            conn.execute(
                """
                INSERT INTO trade_examples
                (source_chunk_id, ticker, direction, instrument_type,
                 trade_date, entry_price, stop_price, target_price, exit_price,
                 entry_description, exit_description, outcome_text,
                 outcome_classification, lessons, confidence,
                 prompt_version, created_at)
                VALUES (?, 'NVDA', 'long', 'stock',
                        NULL, 295.0, NULL, NULL, NULL,
                        'long at 295', 'flat', 'ok',
                        'scratch', NULL, 'high', ?, '2026-05-11')
                """,
                (chunk_id, version),
            )
        conn.commit()
    return chunk_ids[:2]


def test_discover_baseline_chunk_ids_returns_deduped_v1_chunks(
    tmp_path: Path,
) -> None:
    """_discover_baseline_chunk_ids must return unique chunk_ids that have at
    least one v1 TE row, regardless of whether v2 rows exist for the same
    chunk."""
    from trading_wiki.config import PROMPT_VERSION_PASS2_TRADE_EXAMPLE
    from trading_wiki.extractors.pass2.corrective_reextract import (
        _discover_baseline_chunk_ids,
    )

    db_path = tmp_path / "research.db"
    expected = sorted(_seed_baseline_corpus(db_path))

    got = _discover_baseline_chunk_ids(db_path, prompt_version=PROMPT_VERSION_PASS2_TRADE_EXAMPLE)
    assert got == expected
