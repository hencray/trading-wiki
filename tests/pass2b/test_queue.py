"""Tests for the Phase 2B review queue."""

from __future__ import annotations

import sqlite3
from datetime import UTC
from datetime import datetime as _dt
from pathlib import Path


def _seed_corpus_for_queue(db_path: Path) -> dict[str, int]:
    """Seed a DB with one of each trigger-eligible state:
    - one low-confidence Concept
    - one contradicts Relationship between two concepts
    - one Strategy with codeability_score=5 (HARD GATE)
    Returns the inserted entity_ids keyed by short name.
    """
    from trading_wiki.config import (
        PROMPT_VERSION_PASS1,
        PROMPT_VERSION_PASS2_CONCEPT,
        PROMPT_VERSION_PASS2_STRATEGY,
        PROMPT_VERSION_PASS4,
    )
    from trading_wiki.core.db import apply_migrations, save_content_record
    from trading_wiki.handlers.base import ContentRecord, Segment

    apply_migrations(db_path)
    cid = save_content_record(
        db_path,
        ContentRecord(
            source_type="local_video",
            source_id="vid:queue",
            title="queue",
            raw_text="t",
            created_at=_dt(2026, 5, 11, tzinfo=UTC),
            ingested_at=_dt(2026, 5, 11, tzinfo=UTC),
            segments=[Segment(seq=0, text="hi", start_seconds=0.0, end_seconds=1.0)],
        ),
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO chunks
            (content_id, seq, start_seg_seq, end_seg_seq, label, confidence,
             summary, text, prompt_version, created_at)
            VALUES (?, 0, 0, 0, 'strategy', 'high', 's', 't', ?, '2026-05-11')
            """,
            (cid, PROMPT_VERSION_PASS1),
        )
        chunk_id = conn.execute("SELECT id FROM chunks").fetchone()[0]

        # Two concepts so we can build a contradicts relationship
        for term, conf in [("supply", "low"), ("demand", "high")]:
            conn.execute(
                """
                INSERT INTO concepts (source_chunk_id, term, definition,
                                      related_terms, confidence, prompt_version, created_at)
                VALUES (?, ?, 'def', '[]', ?, ?, '2026-05-11')
                """,
                (chunk_id, term, conf, PROMPT_VERSION_PASS2_CONCEPT),
            )
        c_low = conn.execute("SELECT id FROM concepts WHERE term='supply'").fetchone()[0]
        c_high = conn.execute("SELECT id FROM concepts WHERE term='demand'").fetchone()[0]

        # Strategy with codeability=5 — HARD GATE
        conn.execute(
            """
            INSERT INTO strategies (source_chunk_id, name, thesis, entry_rules,
                                     exit_rules, indicators_used, instruments,
                                     codeability_score, confidence, prompt_version, created_at)
            VALUES (?, 'Pure Boolean Breakout', 'A boolean breakout strategy.',
                    'buy on 20-day high', 'sell at 2 ATR stop',
                    '[]', '[]', 5, 'high', ?, '2026-05-11')
            """,
            (chunk_id, PROMPT_VERSION_PASS2_STRATEGY),
        )
        strategy_id = conn.execute("SELECT id FROM strategies").fetchone()[0]

        # Contradicts relationship between the two concepts
        conn.execute(
            """
            INSERT INTO entity_relationships
            (subject_type, subject_id, predicate, object_type, object_id,
             source_chunk_id, confidence, rationale, prompt_version, created_at)
            VALUES ('concept', ?, 'contradicts', 'concept', ?, ?,
                    'high', 'opposing forces', ?, '2026-05-11')
            """,
            (c_low, c_high, chunk_id, PROMPT_VERSION_PASS4),
        )
        rel_id = conn.execute("SELECT id FROM entity_relationships").fetchone()[0]

        conn.commit()
    return {
        "concept_low": c_low,
        "concept_high": c_high,
        "strategy_high_cs": strategy_id,
        "relationship_contradicts": rel_id,
    }


def test_populate_queue_triggers_all_four(tmp_path: Path) -> None:
    from trading_wiki.pass2b.queue import populate_queue

    db_path = tmp_path / "research.db"
    seeded = _seed_corpus_for_queue(db_path)

    result = populate_queue(db_path)
    assert result.low_confidence_added == 1  # supply (concept_low)
    assert result.contradicts_added == 1  # the one contradicts rel
    assert result.codeability_added == 1  # the hard-gate strategy
    assert result.borderline_merge_added == 0  # no concept_resolutions seeded

    # The queue has 3 rows total
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = list(conn.execute("SELECT * FROM review_queue ORDER BY id"))
    assert len(rows) == 3

    # Find the codeability row → it's a hard gate
    cs_rows = [r for r in rows if r["trigger"] == "codeability_4plus"]
    assert len(cs_rows) == 1
    assert cs_rows[0]["is_hard_gate"] == 1
    assert cs_rows[0]["entity_id"] == seeded["strategy_high_cs"]
    assert cs_rows[0]["severity"] == "high"

    # Find the low-confidence row → soft (non-hard-gate)
    lc_rows = [r for r in rows if r["trigger"] == "low_confidence_entity"]
    assert len(lc_rows) == 1
    assert lc_rows[0]["is_hard_gate"] == 0
    assert lc_rows[0]["entity_id"] == seeded["concept_low"]

    # Find the contradicts row → relationship-level
    cr_rows = [r for r in rows if r["trigger"] == "contradicts_relationship"]
    assert len(cr_rows) == 1
    assert cr_rows[0]["relationship_id"] == seeded["relationship_contradicts"]
    assert cr_rows[0]["target_kind"] == "relationship"


def test_populate_queue_is_idempotent(tmp_path: Path) -> None:
    """Running populate_queue twice should not create duplicates."""
    from trading_wiki.pass2b.queue import populate_queue

    db_path = tmp_path / "research.db"
    _seed_corpus_for_queue(db_path)

    first = populate_queue(db_path)
    second = populate_queue(db_path)
    assert first.total_added == 3
    assert second.total_added == 0
    assert second.skipped_duplicates >= 3


def test_check_hard_gate_blocks_pending_high_cs_strategy(tmp_path: Path) -> None:
    """check_hard_gate_for_entity returns (False, [...]) for a strategy with
    a pending codeability_4plus hard-gate row."""
    from trading_wiki.pass2b.queue import check_hard_gate_for_entity, populate_queue

    db_path = tmp_path / "research.db"
    seeded = _seed_corpus_for_queue(db_path)
    populate_queue(db_path)

    allowed, blocking = check_hard_gate_for_entity(
        db_path, entity_type="strategy", entity_id=seeded["strategy_high_cs"]
    )
    assert allowed is False
    assert blocking == ["codeability_4plus"]


def test_check_hard_gate_allows_when_resolved(tmp_path: Path) -> None:
    """Marking the queue row 'accepted' lets the hard gate pass."""
    from trading_wiki.pass2b.queue import check_hard_gate_for_entity, populate_queue

    db_path = tmp_path / "research.db"
    seeded = _seed_corpus_for_queue(db_path)
    populate_queue(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE review_queue
            SET status = 'accepted', resolved_at = '2026-05-11T12:00:00'
            WHERE trigger = 'codeability_4plus'
              AND entity_id = ?
            """,
            (seeded["strategy_high_cs"],),
        )
        conn.commit()

    allowed, blocking = check_hard_gate_for_entity(
        db_path, entity_type="strategy", entity_id=seeded["strategy_high_cs"]
    )
    assert allowed is True
    assert blocking == []


def test_check_hard_gate_allows_for_unrelated_entity(tmp_path: Path) -> None:
    """An entity with no hard-gate rows is allowed."""
    from trading_wiki.pass2b.queue import check_hard_gate_for_entity, populate_queue

    db_path = tmp_path / "research.db"
    seeded = _seed_corpus_for_queue(db_path)
    populate_queue(db_path)

    # The low-confidence Concept has a queue row but NOT a hard-gate one
    allowed, blocking = check_hard_gate_for_entity(
        db_path, entity_type="concept", entity_id=seeded["concept_low"]
    )
    assert allowed is True
    assert blocking == []
