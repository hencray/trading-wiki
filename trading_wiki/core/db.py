import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from yoyo import get_backend, read_migrations

from trading_wiki.handlers.base import ContentRecord, Segment

_MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"


def apply_migrations(
    db_path: Path | str,
    migrations_dir: Path | str | None = None,
) -> None:
    """Apply all pending migrations to the SQLite DB at ``db_path``."""
    migrations_path = Path(migrations_dir) if migrations_dir else _MIGRATIONS_DIR
    backend = get_backend(f"sqlite:///{Path(db_path).resolve()}")
    migrations = read_migrations(str(migrations_path))
    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))


@contextmanager
def _connect(db_path: Path | str) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(Path(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def save_content_record(db_path: Path | str, record: ContentRecord) -> int:
    """Insert a record into the DB. Returns the assigned ``content.id``."""
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO content (
                source_type, source_id, title, author, parent_id,
                created_at, ingested_at, raw_text, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.source_type,
                record.source_id,
                record.title,
                record.author,
                record.parent_id,
                record.created_at.isoformat(),
                record.ingested_at.isoformat(),
                record.raw_text,
                json.dumps(record.metadata),
            ),
        )
        content_id = cursor.lastrowid
        assert content_id is not None
        for segment in record.segments:
            conn.execute(
                """
                INSERT INTO segments (
                    content_id, seq, text, start_seconds, end_seconds
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    content_id,
                    segment.seq,
                    segment.text,
                    segment.start_seconds,
                    segment.end_seconds,
                ),
            )
        return content_id


def load_content_record(
    db_path: Path | str,
    source_type: str,
    source_id: str,
) -> ContentRecord | None:
    """Load a record by ``(source_type, source_id)``; ``None`` if not found."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM content WHERE source_type = ? AND source_id = ?",
            (source_type, source_id),
        ).fetchone()
        if row is None:
            return None
        segment_rows = conn.execute(
            """
            SELECT seq, text, start_seconds, end_seconds
            FROM segments WHERE content_id = ? ORDER BY seq
            """,
            (row["id"],),
        ).fetchall()
        segments = [
            Segment(
                seq=s["seq"],
                text=s["text"],
                start_seconds=s["start_seconds"],
                end_seconds=s["end_seconds"],
            )
            for s in segment_rows
        ]
        return ContentRecord(
            source_type=row["source_type"],
            source_id=row["source_id"],
            title=row["title"],
            author=row["author"],
            parent_id=row["parent_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            ingested_at=datetime.fromisoformat(row["ingested_at"]),
            raw_text=row["raw_text"],
            segments=segments,
            metadata=json.loads(row["metadata"]),
        )
