import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from trading_wiki.core.db import apply_migrations, load_content_record, save_content_record
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
        author="the v1 author",
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
