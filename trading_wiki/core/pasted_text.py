from datetime import datetime
from pathlib import Path

from trading_wiki.core.storage import store_file
from trading_wiki.handlers.base import ContentRecord


def ingest_pasted_text(
    path: Path,
    source_type: str,
    storage_dir: Path,
) -> ContentRecord:
    """Read a pasted-text file, store it content-addressed, return a ContentRecord.

    Used by the Discord and course-platform handlers — both ingest user-pasted
    text where the file *is* the source. ``raw_text`` is the file content
    verbatim; message-level parsing (authors, timestamps, threads) is deferred
    to Phase 2 LLM extraction.
    """
    sha, stored = store_file(path, source_type, storage_dir)
    return ContentRecord(
        source_type=source_type,
        source_id=sha,
        title=path.stem,
        created_at=datetime.fromtimestamp(path.stat().st_mtime),
        ingested_at=datetime.now(),
        raw_text=stored.read_text(encoding="utf-8"),
        metadata={
            "source_path": str(path),
            "stored_path": str(stored),
        },
    )
