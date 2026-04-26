import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from trading_wiki.core.db import (
    apply_migrations,
    list_concepts_for_content,
    list_content_summaries,
    list_trade_examples_for_content,
    load_chunks_for_version,
    load_content_record,
    save_chunks,
    save_concepts,
    save_content_record,
    save_trade_examples,
)
from trading_wiki.extractors.pass1 import Pass1Chunk, Pass1Output
from trading_wiki.extractors.pass2.concept import Concept, ConceptOutput
from trading_wiki.extractors.pass2.trade_example import TradeExample, TradeExampleOutput
from trading_wiki.handlers.base import ContentRecord, Segment


def _table_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {row[0] for row in cursor.fetchall()}
    finally:
        conn.close()


def test_apply_migrations_creates_content_and_segments_tables(tmp_path):
    db_path = tmp_path / "test.db"
    apply_migrations(db_path)
    tables = _table_names(db_path)
    assert "content" in tables
    assert "segments" in tables


def test_apply_migrations_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    apply_migrations(db_path)
    apply_migrations(db_path)
    tables = _table_names(db_path)
    assert "content" in tables
    assert "segments" in tables


def test_save_and_load_content_record_roundtrips(tmp_path):
    db_path = tmp_path / "test.db"
    apply_migrations(db_path)
    record = ContentRecord(
        source_type="local_video",
        source_id="abc123",
        title="lesson 1",
        author="Test Author",
        created_at=datetime(2026, 4, 1, 12, 0, 0),
        ingested_at=datetime(2026, 4, 22, 18, 0, 0),
        raw_text="Hello world.",
        segments=[
            Segment(seq=0, text="part 1", start_seconds=0.0, end_seconds=10.5),
            Segment(seq=1, text="part 2", start_seconds=10.5, end_seconds=20.0),
        ],
        metadata={"channel": "test-channel", "duration_seconds": 1234},
    )
    save_content_record(db_path, record)
    loaded = load_content_record(db_path, source_type="local_video", source_id="abc123")
    assert loaded == record


def test_load_content_record_returns_none_when_missing(tmp_path):
    db_path = tmp_path / "test.db"
    apply_migrations(db_path)
    loaded = load_content_record(db_path, source_type="x", source_id="missing")
    assert loaded is None


def test_content_exists(tmp_path):
    from trading_wiki.core.db import content_exists

    db_path = tmp_path / "research.db"
    apply_migrations(db_path)
    assert content_exists(db_path, content_id=1) is False

    record = ContentRecord(
        source_type="t",
        source_id="a",
        title="t",
        created_at=datetime(2026, 4, 25),
        ingested_at=datetime(2026, 4, 25),
        raw_text="r",
        segments=[Segment(seq=0, text="x")],
    )
    cid = save_content_record(db_path, record)
    assert content_exists(db_path, content_id=cid) is True


def test_load_segments_for_content_id(tmp_path):
    from trading_wiki.core.db import load_segments_for_content_id

    db_path = tmp_path / "research.db"
    apply_migrations(db_path)
    record = ContentRecord(
        source_type="t",
        source_id="a",
        title="t",
        created_at=datetime(2026, 4, 25),
        ingested_at=datetime(2026, 4, 25),
        raw_text="r",
        segments=[
            Segment(seq=0, text="hello", start_seconds=0.0, end_seconds=1.0),
            Segment(seq=1, text="world", start_seconds=1.0, end_seconds=2.0),
        ],
    )
    cid = save_content_record(db_path, record)
    segs = load_segments_for_content_id(db_path, content_id=cid)
    assert [s.seq for s in segs] == [0, 1]
    assert segs[0].text == "hello"
    assert segs[1].start_seconds == 1.0
    assert load_segments_for_content_id(db_path, content_id=999) == []


def test_save_and_load_chunks(tmp_path):
    from trading_wiki.core.db import load_chunks_for_version, save_chunks
    from trading_wiki.extractors.pass1 import Pass1Chunk, Pass1Output

    db_path = tmp_path / "research.db"
    apply_migrations(db_path)

    record = ContentRecord(
        source_type="test",
        source_id="vid1",
        title="Test",
        created_at=datetime(2026, 4, 25),
        ingested_at=datetime(2026, 4, 25),
        raw_text="hello world",
        segments=[
            Segment(seq=0, text="hello", start_seconds=0.0, end_seconds=1.0),
            Segment(seq=1, text="world", start_seconds=1.0, end_seconds=2.0),
        ],
    )
    content_id = save_content_record(db_path, record)

    output = Pass1Output(
        chunks=[
            Pass1Chunk(
                seq=0,
                start_seg_seq=0,
                end_seg_seq=1,
                label="noise",
                confidence="high",
                summary="greeting",
            ),
        ]
    )
    save_chunks(db_path, content_id=content_id, prompt_version="pass1-v1", output=output)

    rows = load_chunks_for_version(db_path, content_id=content_id, prompt_version="pass1-v1")
    assert len(rows) == 1
    assert rows[0]["seq"] == 0
    assert rows[0]["label"] == "noise"
    assert rows[0]["summary"] == "greeting"
    assert rows[0]["start_seconds"] == 0.0
    assert rows[0]["end_seconds"] == 2.0
    assert rows[0]["text"] == "hello\nworld"

    assert load_chunks_for_version(db_path, content_id=content_id, prompt_version="pass1-v2") == []


def test_save_chunks_rolls_back_on_error(tmp_path):
    from trading_wiki.core.db import load_chunks_for_version, save_chunks
    from trading_wiki.extractors.pass1 import Pass1Chunk, Pass1Output

    db_path = tmp_path / "research.db"
    apply_migrations(db_path)

    record = ContentRecord(
        source_type="test",
        source_id="vid1",
        title="t",
        created_at=datetime(2026, 4, 25),
        ingested_at=datetime(2026, 4, 25),
        raw_text="hello",
        segments=[Segment(seq=0, text="hello", start_seconds=0.0, end_seconds=1.0)],
    )
    content_id = save_content_record(db_path, record)

    output1 = Pass1Output(
        chunks=[
            Pass1Chunk(
                seq=0,
                start_seg_seq=0,
                end_seg_seq=0,
                label="noise",
                confidence="high",
                summary="x",
            ),
        ]
    )
    save_chunks(db_path, content_id=content_id, prompt_version="v1", output=output1)

    output2 = Pass1Output(
        chunks=[
            Pass1Chunk(
                seq=0,
                start_seg_seq=0,
                end_seg_seq=0,
                label="strategy",
                confidence="high",
                summary="y",
            ),
            Pass1Chunk(
                seq=1,
                start_seg_seq=0,
                end_seg_seq=0,
                label="concept",
                confidence="high",
                summary="z",
            ),
        ]
    )
    with pytest.raises(sqlite3.IntegrityError):
        save_chunks(db_path, content_id=content_id, prompt_version="v1", output=output2)

    rows = load_chunks_for_version(db_path, content_id=content_id, prompt_version="v1")
    assert len(rows) == 1
    assert rows[0]["label"] == "noise"


def test_migration_0002_creates_chunks_table(tmp_path):
    """0002 creates a chunks table with the columns and CHECK constraints from spec §5.1."""
    db_path = tmp_path / "research.db"
    apply_migrations(db_path)

    with sqlite3.connect(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(chunks)").fetchall()}
        assert cols == {
            "id",
            "content_id",
            "seq",
            "start_seg_seq",
            "end_seg_seq",
            "start_seconds",
            "end_seconds",
            "label",
            "confidence",
            "summary",
            "text",
            "prompt_version",
            "created_at",
        }

        conn.execute(
            "INSERT INTO content "
            "(source_type, source_id, title, created_at, ingested_at, raw_text) "
            "VALUES ('test', 'a', 't', '2026-01-01', '2026-01-01', 'r')"
        )
        content_id = conn.execute("SELECT id FROM content").fetchone()[0]

        bad_label = (
            "INSERT INTO chunks (content_id, seq, start_seg_seq, end_seg_seq, "
            "label, confidence, summary, text, prompt_version, created_at) "
            "VALUES (?, 0, 0, 0, 'not_a_label', 'high', 's', 't', 'v', '2026-01-01')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(bad_label, (content_id,))

        bad_conf = (
            "INSERT INTO chunks (content_id, seq, start_seg_seq, end_seg_seq, "
            "label, confidence, summary, text, prompt_version, created_at) "
            "VALUES (?, 0, 0, 0, 'noise', 'maybe', 's', 't', 'v', '2026-01-01')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(bad_conf, (content_id,))

        good = (
            "INSERT INTO chunks (content_id, seq, start_seg_seq, end_seg_seq, "
            "label, confidence, summary, text, prompt_version, created_at) "
            "VALUES (?, 0, 0, 0, 'noise', 'high', 's', 't', 'pass1-v1', '2026-01-01')"
        )
        conn.execute(good, (content_id,))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(good, (content_id,))


def test_migration_0003_creates_trade_examples_table(tmp_path):
    """0003 creates a trade_examples table with the columns and CHECK constraints from spec §5.1."""
    import sqlite3

    from trading_wiki.core.db import apply_migrations

    db_path = tmp_path / "research.db"
    apply_migrations(db_path)

    with sqlite3.connect(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(trade_examples)").fetchall()}
        assert cols == {
            "id",
            "source_chunk_id",
            "ticker",
            "direction",
            "instrument_type",
            "trade_date",
            "entry_price",
            "stop_price",
            "target_price",
            "exit_price",
            "entry_description",
            "exit_description",
            "outcome_text",
            "outcome_classification",
            "lessons",
            "confidence",
            "prompt_version",
            "created_at",
        }

        # Seed a content + chunk so the FK resolves.
        conn.execute(
            "INSERT INTO content "
            "(source_type, source_id, title, created_at, ingested_at, raw_text) "
            "VALUES ('test', 'a', 't', '2026-01-01', '2026-01-01', 'r')"
        )
        content_id = conn.execute("SELECT id FROM content").fetchone()[0]
        conn.execute(
            "INSERT INTO chunks (content_id, seq, start_seg_seq, end_seg_seq, "
            "label, confidence, summary, text, prompt_version, created_at) "
            "VALUES (?, 0, 0, 0, 'example', 'high', 's', 't', 'pass1-v1', '2026-01-01')",
            (content_id,),
        )
        chunk_id = conn.execute("SELECT id FROM chunks").fetchone()[0]

        ok_insert = (
            "INSERT INTO trade_examples (source_chunk_id, ticker, direction, instrument_type, "
            "entry_description, exit_description, outcome_text, confidence, "
            "prompt_version, created_at) "
            "VALUES (?, 'NVDA', 'long', 'stock', 'in at 850', 'out at 858', "
            "'won', 'high', 'v', '2026-01-01')"
        )
        conn.execute(ok_insert, (chunk_id,))

        # CHECK constraint on direction rejects unknown values.
        bad_dir = (
            "INSERT INTO trade_examples (source_chunk_id, ticker, direction, instrument_type, "
            "entry_description, exit_description, outcome_text, confidence, "
            "prompt_version, created_at) "
            "VALUES (?, 'NVDA', 'sideways', 'stock', 'i', 'o', 'w', 'high', 'v', '2026-01-01')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(bad_dir, (chunk_id,))

        # CHECK constraint on instrument_type rejects unknown values.
        bad_inst = (
            "INSERT INTO trade_examples (source_chunk_id, ticker, direction, instrument_type, "
            "entry_description, exit_description, outcome_text, confidence, "
            "prompt_version, created_at) "
            "VALUES (?, 'NVDA', 'long', 'commodity', 'i', 'o', 'w', 'high', 'v', '2026-01-01')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(bad_inst, (chunk_id,))

        # CHECK constraint on outcome_classification accepts NULL but rejects bad values.
        bad_outcome = (
            "INSERT INTO trade_examples (source_chunk_id, ticker, direction, instrument_type, "
            "entry_description, exit_description, outcome_text, outcome_classification, "
            "confidence, prompt_version, created_at) "
            "VALUES (?, 'NVDA', 'long', 'stock', 'i', 'o', 'w', 'maybe', 'high', 'v', '2026-01-01')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(bad_outcome, (chunk_id,))

        # CHECK constraint on confidence rejects unknown values.
        bad_conf = (
            "INSERT INTO trade_examples (source_chunk_id, ticker, direction, instrument_type, "
            "entry_description, exit_description, outcome_text, confidence, "
            "prompt_version, created_at) "
            "VALUES (?, 'NVDA', 'long', 'stock', 'i', 'o', 'w', 'mid', 'v', '2026-01-01')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(bad_conf, (chunk_id,))


def test_migration_0004_creates_concepts_table(tmp_path):
    """0004 creates a concepts table with the columns and CHECK constraints from spec §5.1."""
    import sqlite3

    from trading_wiki.core.db import apply_migrations

    db_path = tmp_path / "research.db"
    apply_migrations(db_path)

    with sqlite3.connect(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(concepts)").fetchall()}
        assert cols == {
            "id",
            "source_chunk_id",
            "term",
            "definition",
            "related_terms",
            "confidence",
            "prompt_version",
            "created_at",
        }

        # Seed a content + chunk so the FK resolves.
        conn.execute(
            "INSERT INTO content "
            "(source_type, source_id, title, created_at, ingested_at, raw_text) "
            "VALUES ('test', 'a', 't', '2026-01-01', '2026-01-01', 'r')"
        )
        content_id = conn.execute("SELECT id FROM content").fetchone()[0]
        conn.execute(
            "INSERT INTO chunks (content_id, seq, start_seg_seq, end_seg_seq, "
            "label, confidence, summary, text, prompt_version, created_at) "
            "VALUES (?, 0, 0, 0, 'concept', 'high', 's', 't', 'pass1-v1', '2026-01-01')",
            (content_id,),
        )
        chunk_id = conn.execute("SELECT id FROM chunks").fetchone()[0]

        # Happy-path insert.
        conn.execute(
            "INSERT INTO concepts (source_chunk_id, term, definition, related_terms, "
            "confidence, prompt_version, created_at) "
            "VALUES (?, 'pivot', 'avg of HLC', '[\"resistance\"]', "
            "'high', 'v', '2026-01-01')",
            (chunk_id,),
        )

        # CHECK constraint on confidence rejects unknown values.
        bad_conf = (
            "INSERT INTO concepts (source_chunk_id, term, definition, related_terms, "
            "confidence, prompt_version, created_at) "
            "VALUES (?, 'pivot', 'def', '[]', 'maybe', 'v', '2026-01-01')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(bad_conf, (chunk_id,))

        # related_terms defaults to '[]' when omitted.
        conn.execute(
            "INSERT INTO concepts (source_chunk_id, term, definition, "
            "confidence, prompt_version, created_at) "
            "VALUES (?, 'breakout', 'def2', 'high', 'v', '2026-01-01')",
            (chunk_id,),
        )
        row = conn.execute("SELECT related_terms FROM concepts WHERE term = 'breakout'").fetchone()
        assert row[0] == "[]"


def test_load_chunk_by_id_returns_row(tmp_path):
    from trading_wiki.core.db import (
        load_chunk_by_id,
        save_chunks,
    )
    from trading_wiki.extractors.pass1 import Pass1Chunk, Pass1Output

    db_path = tmp_path / "research.db"
    apply_migrations(db_path)

    record = ContentRecord(
        source_type="test",
        source_id="vid1",
        title="t",
        created_at=datetime(2026, 4, 25),
        ingested_at=datetime(2026, 4, 25),
        raw_text="hello world",
        segments=[
            Segment(seq=0, text="hello", start_seconds=0.0, end_seconds=1.0),
            Segment(seq=1, text="world", start_seconds=1.0, end_seconds=2.0),
        ],
    )
    content_id = save_content_record(db_path, record)
    save_chunks(
        db_path,
        content_id=content_id,
        prompt_version="pass1-v1",
        output=Pass1Output(
            chunks=[
                Pass1Chunk(
                    seq=0,
                    start_seg_seq=0,
                    end_seg_seq=1,
                    label="example",
                    confidence="high",
                    summary="trade walkthrough",
                ),
            ]
        ),
    )
    with sqlite3.connect(db_path) as conn:
        chunk_id = conn.execute("SELECT id FROM chunks").fetchone()[0]

    row = load_chunk_by_id(db_path, chunk_id=chunk_id)
    assert row is not None
    assert row["label"] == "example"
    assert row["text"] == "hello\nworld"
    assert row["content_id"] == content_id


def test_load_chunk_by_id_returns_none_when_missing(tmp_path):
    from trading_wiki.core.db import load_chunk_by_id

    db_path = tmp_path / "research.db"
    apply_migrations(db_path)
    assert load_chunk_by_id(db_path, chunk_id=999) is None


def test_save_and_load_trade_examples(tmp_path):
    """save_trade_examples writes all rows in one transaction; loader reads them back."""
    from trading_wiki.core.db import (
        load_trade_examples_for_version,
        save_chunks,
        save_trade_examples,
    )
    from trading_wiki.extractors.pass1 import Pass1Chunk, Pass1Output
    from trading_wiki.extractors.pass2.trade_example import (
        TradeExample,
        TradeExampleOutput,
    )

    db_path = tmp_path / "research.db"
    apply_migrations(db_path)
    record = ContentRecord(
        source_type="t",
        source_id="a",
        title="t",
        created_at=datetime(2026, 4, 25),
        ingested_at=datetime(2026, 4, 25),
        raw_text="r",
        segments=[Segment(seq=0, text="x")],
    )
    content_id = save_content_record(db_path, record)
    save_chunks(
        db_path,
        content_id=content_id,
        prompt_version="pass1-v1",
        output=Pass1Output(
            chunks=[
                Pass1Chunk(
                    seq=0,
                    start_seg_seq=0,
                    end_seg_seq=0,
                    label="example",
                    confidence="high",
                    summary="x",
                ),
            ]
        ),
    )
    with sqlite3.connect(db_path) as conn:
        chunk_id = conn.execute("SELECT id FROM chunks").fetchone()[0]

    out = TradeExampleOutput(
        entities=[
            TradeExample(
                ticker="NVDA",
                direction="long",
                instrument_type="stock",
                trade_date="2026-03-05",
                entry_price=846.0,
                exit_price=857.5,
                entry_description="in at 846",
                exit_description="out at 857.5",
                outcome_text="won 11R",
                outcome_classification="won",
                confidence="high",
            ),
            TradeExample(
                ticker="BKSY",
                direction="short",
                instrument_type="stock",
                entry_description="entered short",
                exit_description="covered",
                outcome_text="lost 1R",
                outcome_classification="lost",
                confidence="medium",
            ),
        ]
    )
    save_trade_examples(
        db_path,
        source_chunk_id=chunk_id,
        prompt_version="pass2-trade-example-v1",
        output=out,
    )

    rows = load_trade_examples_for_version(
        db_path,
        source_chunk_id=chunk_id,
        prompt_version="pass2-trade-example-v1",
    )
    assert len(rows) == 2
    nvda = next(r for r in rows if r["ticker"] == "NVDA")
    assert nvda["direction"] == "long"
    assert nvda["entry_price"] == 846.0
    assert nvda["outcome_classification"] == "won"
    bksy = next(r for r in rows if r["ticker"] == "BKSY")
    assert bksy["entry_price"] is None
    assert bksy["outcome_classification"] == "lost"

    # Different prompt version → empty.
    assert (
        load_trade_examples_for_version(
            db_path,
            source_chunk_id=chunk_id,
            prompt_version="pass2-trade-example-v2",
        )
        == []
    )


def test_save_trade_examples_rolls_back_on_error(tmp_path):
    """If any insert fails (CHECK violation), no rows for that call should land."""
    from unittest.mock import patch

    from trading_wiki.core.db import (
        load_trade_examples_for_version,
        save_chunks,
        save_trade_examples,
    )
    from trading_wiki.extractors.pass1 import Pass1Chunk, Pass1Output
    from trading_wiki.extractors.pass2.trade_example import (
        TradeExample,
        TradeExampleOutput,
    )

    db_path = tmp_path / "research.db"
    apply_migrations(db_path)
    record = ContentRecord(
        source_type="t",
        source_id="a",
        title="t",
        created_at=datetime(2026, 4, 25),
        ingested_at=datetime(2026, 4, 25),
        raw_text="r",
        segments=[Segment(seq=0, text="x")],
    )
    content_id = save_content_record(db_path, record)
    save_chunks(
        db_path,
        content_id=content_id,
        prompt_version="pass1-v1",
        output=Pass1Output(
            chunks=[
                Pass1Chunk(
                    seq=0,
                    start_seg_seq=0,
                    end_seg_seq=0,
                    label="example",
                    confidence="high",
                    summary="x",
                ),
            ]
        ),
    )
    with sqlite3.connect(db_path) as conn:
        chunk_id = conn.execute("SELECT id FROM chunks").fetchone()[0]

    good = TradeExample(
        ticker="NVDA",
        direction="long",
        instrument_type="stock",
        entry_description="i",
        exit_description="o",
        outcome_text="w",
        confidence="high",
    )
    out = TradeExampleOutput(entities=[good, good])

    real_dump = TradeExample.model_dump
    call_count = {"n": 0}

    def flaky_dump(self, **kwargs):
        result = real_dump(self, **kwargs)
        call_count["n"] += 1
        if call_count["n"] == 2:
            result["direction"] = "sideways"  # rejected by DB CHECK
        return result

    with (
        patch.object(TradeExample, "model_dump", flaky_dump),
        pytest.raises(sqlite3.IntegrityError),
    ):
        save_trade_examples(
            db_path,
            source_chunk_id=chunk_id,
            prompt_version="pass2-trade-example-v1",
            output=out,
        )

    rows = load_trade_examples_for_version(
        db_path,
        source_chunk_id=chunk_id,
        prompt_version="pass2-trade-example-v1",
    )
    assert rows == []


def test_save_and_load_concepts(tmp_path):
    """save_concepts writes all rows in one transaction; loader returns related_terms as list."""
    from trading_wiki.core.db import (
        load_concepts_for_version,
        save_chunks,
        save_concepts,
    )
    from trading_wiki.extractors.pass1 import Pass1Chunk, Pass1Output
    from trading_wiki.extractors.pass2.concept import Concept, ConceptOutput

    db_path = tmp_path / "research.db"
    apply_migrations(db_path)
    record = ContentRecord(
        source_type="t",
        source_id="a",
        title="t",
        created_at=datetime(2026, 4, 25),
        ingested_at=datetime(2026, 4, 25),
        raw_text="r",
        segments=[Segment(seq=0, text="x")],
    )
    content_id = save_content_record(db_path, record)
    save_chunks(
        db_path,
        content_id=content_id,
        prompt_version="pass1-v1",
        output=Pass1Output(
            chunks=[
                Pass1Chunk(
                    seq=0,
                    start_seg_seq=0,
                    end_seg_seq=0,
                    label="concept",
                    confidence="high",
                    summary="x",
                ),
            ]
        ),
    )
    with sqlite3.connect(db_path) as conn:
        chunk_id = conn.execute("SELECT id FROM chunks").fetchone()[0]

    out = ConceptOutput(
        entities=[
            Concept(
                term="pivot point",
                definition="Average of prior period's high, low, and close.",
                related_terms=["resistance", "support"],
                confidence="high",
            ),
            Concept(
                term="pullback hold",
                definition="Setup where price reclaims pivot in the first hour.",
                related_terms=[],
                confidence="medium",
            ),
        ]
    )
    save_concepts(
        db_path,
        source_chunk_id=chunk_id,
        prompt_version="pass2-concept-v1",
        output=out,
    )

    rows = load_concepts_for_version(
        db_path,
        source_chunk_id=chunk_id,
        prompt_version="pass2-concept-v1",
    )
    assert len(rows) == 2
    pp = next(r for r in rows if r["term"] == "pivot point")
    # related_terms is JSON-decoded into a Python list on read.
    assert pp["related_terms"] == ["resistance", "support"]
    pre = next(r for r in rows if r["term"] == "pullback hold")
    assert pre["related_terms"] == []

    # Different prompt version → empty.
    assert (
        load_concepts_for_version(
            db_path,
            source_chunk_id=chunk_id,
            prompt_version="pass2-concept-v2",
        )
        == []
    )


def test_save_concepts_rolls_back_on_error(tmp_path):
    """If any insert fails (CHECK violation), no concepts for that call should land."""
    from unittest.mock import patch

    from trading_wiki.core.db import (
        load_concepts_for_version,
        save_chunks,
        save_concepts,
    )
    from trading_wiki.extractors.pass1 import Pass1Chunk, Pass1Output
    from trading_wiki.extractors.pass2.concept import Concept, ConceptOutput

    db_path = tmp_path / "research.db"
    apply_migrations(db_path)
    record = ContentRecord(
        source_type="t",
        source_id="a",
        title="t",
        created_at=datetime(2026, 4, 25),
        ingested_at=datetime(2026, 4, 25),
        raw_text="r",
        segments=[Segment(seq=0, text="x")],
    )
    content_id = save_content_record(db_path, record)
    save_chunks(
        db_path,
        content_id=content_id,
        prompt_version="pass1-v1",
        output=Pass1Output(
            chunks=[
                Pass1Chunk(
                    seq=0,
                    start_seg_seq=0,
                    end_seg_seq=0,
                    label="concept",
                    confidence="high",
                    summary="x",
                ),
            ]
        ),
    )
    with sqlite3.connect(db_path) as conn:
        chunk_id = conn.execute("SELECT id FROM chunks").fetchone()[0]

    good = Concept(
        term="pivot",
        definition="A pivot is a level.",
        confidence="high",
    )
    out = ConceptOutput(entities=[good, good])

    real_dump = Concept.model_dump
    call_count = {"n": 0}

    def flaky_dump(self, **kwargs):
        result = real_dump(self, **kwargs)
        call_count["n"] += 1
        if call_count["n"] == 2:
            result["confidence"] = "mid"  # rejected by DB CHECK
        return result

    with (
        patch.object(Concept, "model_dump", flaky_dump),
        pytest.raises(sqlite3.IntegrityError),
    ):
        save_concepts(
            db_path,
            source_chunk_id=chunk_id,
            prompt_version="pass2-concept-v1",
            output=out,
        )

    rows = load_concepts_for_version(
        db_path,
        source_chunk_id=chunk_id,
        prompt_version="pass2-concept-v1",
    )
    assert rows == []


def test_list_content_summaries_returns_id_type_title(tmp_path):
    db_path = tmp_path / "test.db"
    apply_migrations(db_path)
    save_content_record(
        db_path,
        ContentRecord(
            source_type="local_video",
            source_id="aaa",
            title="first",
            author=None,
            created_at=datetime(2026, 4, 1),
            ingested_at=datetime(2026, 4, 22),
            raw_text="x",
            segments=[Segment(seq=0, text="x", start_seconds=0.0, end_seconds=1.0)],
        ),
    )
    save_content_record(
        db_path,
        ContentRecord(
            source_type="youtube",
            source_id="bbb",
            title="second",
            author=None,
            created_at=datetime(2026, 4, 2),
            ingested_at=datetime(2026, 4, 23),
            raw_text="y",
            segments=[Segment(seq=0, text="y", start_seconds=0.0, end_seconds=1.0)],
        ),
    )

    rows = list_content_summaries(db_path)

    assert [r["title"] for r in rows] == ["first", "second"]
    assert {r["source_type"] for r in rows} == {"local_video", "youtube"}
    assert all(isinstance(r["id"], int) for r in rows)


def test_list_content_summaries_empty_db_returns_empty_list(tmp_path):
    db_path = tmp_path / "test.db"
    apply_migrations(db_path)
    assert list_content_summaries(db_path) == []


def test_list_trade_examples_for_content_returns_only_matching_content(tmp_path):
    db_path = tmp_path / "test.db"
    apply_migrations(db_path)
    cid_a = save_content_record(
        db_path,
        ContentRecord(
            source_type="local_video",
            source_id="a",
            title="A",
            author=None,
            created_at=datetime(2026, 4, 1),
            ingested_at=datetime(2026, 4, 22),
            raw_text="hello",
            segments=[Segment(seq=0, text="hello", start_seconds=0.0, end_seconds=1.0)],
        ),
    )
    save_chunks(
        db_path,
        content_id=cid_a,
        prompt_version="pass1-v1",
        output=Pass1Output(
            chunks=[
                Pass1Chunk(
                    seq=0,
                    start_seg_seq=0,
                    end_seg_seq=0,
                    label="example",
                    confidence="high",
                    summary="trade",
                ),
            ]
        ),
    )
    chunk_a = load_chunks_for_version(db_path, content_id=cid_a, prompt_version="pass1-v1")[0]
    save_trade_examples(
        db_path,
        source_chunk_id=chunk_a["id"],
        prompt_version="pass2-trade-example-v1",
        output=TradeExampleOutput(
            entities=[
                TradeExample(
                    ticker="AAPL",
                    direction="long",
                    instrument_type="stock",
                    trade_date=None,
                    entry_price=100.0,
                    stop_price=99.0,
                    target_price=110.0,
                    exit_price=105.0,
                    entry_description="enter on breakout",
                    exit_description="exit at target",
                    outcome_text="closed at target",
                    outcome_classification="won",
                    lessons=None,
                    confidence="high",
                )
            ]
        ),
    )
    cid_b = save_content_record(
        db_path,
        ContentRecord(
            source_type="local_video",
            source_id="b",
            title="B",
            author=None,
            created_at=datetime(2026, 4, 2),
            ingested_at=datetime(2026, 4, 23),
            raw_text="bye",
            segments=[Segment(seq=0, text="bye", start_seconds=0.0, end_seconds=1.0)],
        ),
    )

    rows_a = list_trade_examples_for_content(db_path, content_id=cid_a)
    rows_b = list_trade_examples_for_content(db_path, content_id=cid_b)

    assert len(rows_a) == 1
    assert rows_a[0]["ticker"] == "AAPL"
    assert rows_a[0]["source_chunk_id"] == chunk_a["id"]
    assert rows_b == []


def test_list_concepts_for_content_returns_decoded_related_terms(tmp_path):
    db_path = tmp_path / "test.db"
    apply_migrations(db_path)
    cid = save_content_record(
        db_path,
        ContentRecord(
            source_type="local_video",
            source_id="a",
            title="A",
            author=None,
            created_at=datetime(2026, 4, 1),
            ingested_at=datetime(2026, 4, 22),
            raw_text="vwap is volume weighted",
            segments=[
                Segment(
                    seq=0,
                    text="vwap is volume weighted",
                    start_seconds=0.0,
                    end_seconds=1.0,
                )
            ],
        ),
    )
    save_chunks(
        db_path,
        content_id=cid,
        prompt_version="pass1-v1",
        output=Pass1Output(
            chunks=[
                Pass1Chunk(
                    seq=0,
                    start_seg_seq=0,
                    end_seg_seq=0,
                    label="concept",
                    confidence="high",
                    summary="vwap concept",
                ),
            ]
        ),
    )
    chunk = load_chunks_for_version(db_path, content_id=cid, prompt_version="pass1-v1")[0]
    save_concepts(
        db_path,
        source_chunk_id=chunk["id"],
        prompt_version="pass2-concept-v1",
        output=ConceptOutput(
            entities=[
                Concept(
                    term="VWAP",
                    definition="volume-weighted average price across the session",
                    related_terms=["vwap", "average price"],
                    confidence="high",
                )
            ]
        ),
    )

    rows = list_concepts_for_content(db_path, content_id=cid)

    assert len(rows) == 1
    assert rows[0]["term"] == "VWAP"
    assert rows[0]["related_terms"] == ["vwap", "average price"]
    assert rows[0]["source_chunk_id"] == chunk["id"]
