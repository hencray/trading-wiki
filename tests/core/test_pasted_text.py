from datetime import datetime
from pathlib import Path

import pytest

from trading_wiki.core.pasted_text import ingest_pasted_text
from trading_wiki.core.storage import compute_file_hash


def _write_paste(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_returns_content_record_with_source_type(tmp_path):
    src = _write_paste(tmp_path, "discord-channel.txt", "[Author] hello")

    record = ingest_pasted_text(src, "discord", tmp_path / "storage")

    assert record.source_type == "discord"


def test_source_id_is_sha256_of_file(tmp_path):
    src = _write_paste(tmp_path, "paste.txt", "hello world")

    record = ingest_pasted_text(src, "discord", tmp_path / "storage")

    assert record.source_id == compute_file_hash(src)


def test_raw_text_matches_file_contents(tmp_path):
    body = "line one\nline two\nline three\n"
    src = _write_paste(tmp_path, "paste.txt", body)

    record = ingest_pasted_text(src, "discord", tmp_path / "storage")

    assert record.raw_text == body


def test_raw_text_preserves_utf8_characters(tmp_path):
    body = "résumé — naïve façade · 🚀 strategy"
    src = _write_paste(tmp_path, "paste.txt", body)

    record = ingest_pasted_text(src, "discord", tmp_path / "storage")

    assert record.raw_text == body


def test_title_is_file_stem(tmp_path):
    src = _write_paste(tmp_path, "pivots-channel.txt", "x")

    record = ingest_pasted_text(src, "discord", tmp_path / "storage")

    assert record.title == "pivots-channel"


def test_created_at_uses_file_mtime(tmp_path):
    src = _write_paste(tmp_path, "paste.txt", "x")
    expected = datetime.fromtimestamp(src.stat().st_mtime)

    record = ingest_pasted_text(src, "discord", tmp_path / "storage")

    assert record.created_at == expected


def test_stores_file_content_addressed(tmp_path):
    src = _write_paste(tmp_path, "paste.txt", "hello")

    record = ingest_pasted_text(src, "discord", tmp_path / "storage")

    sha = record.source_id
    expected = tmp_path / "storage" / "discord" / sha[:2] / f"{sha}.txt"
    assert expected.exists()
    assert expected.read_text(encoding="utf-8") == "hello"


def test_idempotent_when_called_twice(tmp_path):
    src = _write_paste(tmp_path, "paste.txt", "hello")
    storage = tmp_path / "storage"

    first = ingest_pasted_text(src, "discord", storage)
    second = ingest_pasted_text(src, "discord", storage)

    assert first.source_id == second.source_id
    assert first.metadata["stored_path"] == second.metadata["stored_path"]


def test_metadata_records_source_and_stored_paths(tmp_path):
    src = _write_paste(tmp_path, "paste.txt", "hello")

    record = ingest_pasted_text(src, "discord", tmp_path / "storage")

    assert record.metadata["source_path"] == str(src)
    assert record.metadata["stored_path"].endswith(f"{record.source_id}.txt")


def test_segments_default_to_empty_list(tmp_path):
    src = _write_paste(tmp_path, "paste.txt", "hello")

    record = ingest_pasted_text(src, "discord", tmp_path / "storage")

    assert record.segments == []


def test_uses_caller_supplied_source_type(tmp_path):
    src = _write_paste(tmp_path, "paste.txt", "hello")

    record = ingest_pasted_text(src, "course_platform", tmp_path / "storage")

    assert record.source_type == "course_platform"
    sha = record.source_id
    expected = tmp_path / "storage" / "course_platform" / sha[:2] / f"{sha}.txt"
    assert expected.exists()


def test_missing_file_raises(tmp_path):
    src = tmp_path / "does-not-exist.txt"

    with pytest.raises(FileNotFoundError):
        ingest_pasted_text(src, "discord", tmp_path / "storage")
