import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yoyo import get_backend, read_migrations

from trading_wiki.handlers.base import ContentRecord, Segment

if TYPE_CHECKING:
    from trading_wiki.extractors.pass1 import Pass1Output

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


def content_exists(db_path: Path | str, *, content_id: int) -> bool:
    """Return whether a content row with the given id exists."""
    with _connect(db_path) as conn:
        row = conn.execute("SELECT 1 FROM content WHERE id = ?", (content_id,)).fetchone()
        return row is not None


def load_segments_for_content_id(
    db_path: Path | str,
    *,
    content_id: int,
) -> list[Segment]:
    """Load all segments for a given content_id, ordered by seq."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT seq, text, start_seconds, end_seconds FROM segments "
            "WHERE content_id = ? ORDER BY seq",
            (content_id,),
        ).fetchall()
        return [
            Segment(
                seq=r["seq"],
                text=r["text"],
                start_seconds=r["start_seconds"],
                end_seconds=r["end_seconds"],
            )
            for r in rows
        ]


def save_chunks(
    db_path: Path | str,
    *,
    content_id: int,
    prompt_version: str,
    output: "Pass1Output",
) -> None:
    """Write all chunks from a Pass1Output in a single transaction.

    Denormalises start_seconds / end_seconds / text from the segments table.
    Raises sqlite3.IntegrityError on UNIQUE violation; the transaction is
    rolled back so partial writes don't land.
    """
    now = datetime.now().isoformat()
    with _connect(db_path) as conn:
        seg_rows = conn.execute(
            "SELECT seq, start_seconds, end_seconds, text FROM segments "
            "WHERE content_id = ? ORDER BY seq",
            (content_id,),
        ).fetchall()
        seg_meta = {r["seq"]: (r["start_seconds"], r["end_seconds"], r["text"]) for r in seg_rows}

        for chunk in output.chunks:
            start_secs = seg_meta.get(chunk.start_seg_seq, (None, None, ""))[0]
            end_secs = seg_meta.get(chunk.end_seg_seq, (None, None, ""))[1]
            text = "\n".join(
                seg_meta[seq][2]
                for seq in range(chunk.start_seg_seq, chunk.end_seg_seq + 1)
                if seq in seg_meta
            )
            conn.execute(
                """
                INSERT INTO chunks (
                    content_id, seq, start_seg_seq, end_seg_seq,
                    start_seconds, end_seconds, label, confidence,
                    summary, text, prompt_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    content_id,
                    chunk.seq,
                    chunk.start_seg_seq,
                    chunk.end_seg_seq,
                    start_secs,
                    end_secs,
                    chunk.label,
                    chunk.confidence,
                    chunk.summary,
                    text,
                    prompt_version,
                    now,
                ),
            )


def load_chunks_for_version(
    db_path: Path | str,
    *,
    content_id: int,
    prompt_version: str,
) -> list[dict[str, Any]]:
    """Return chunk rows for ``(content_id, prompt_version)`` ordered by seq."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM chunks WHERE content_id = ? AND prompt_version = ? ORDER BY seq",
            (content_id, prompt_version),
        ).fetchall()
        return [dict(row) for row in rows]
