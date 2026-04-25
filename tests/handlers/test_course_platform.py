from pathlib import Path

import pytest

from trading_wiki.core.storage import compute_file_hash
from trading_wiki.handlers.course_platform import CoursePlatformHandler


def _write_paste(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_can_handle_course_prefix(tmp_path):
    handler = CoursePlatformHandler(storage_dir=tmp_path / "storage")
    assert handler.can_handle("course:/abs/path/lesson.txt") is True
    assert handler.can_handle("course:relative/lesson.txt") is True
    assert handler.can_handle("course:") is True


def test_does_not_handle_other_sources(tmp_path):
    handler = CoursePlatformHandler(storage_dir=tmp_path / "storage")
    assert handler.can_handle("/local/video.mp4") is False
    assert handler.can_handle("https://youtube.com/watch?v=abc") is False
    assert handler.can_handle("discord:/path/paste.txt") is False
    assert handler.can_handle("notes.txt") is False


def test_ingest_returns_content_record_with_course_platform_source_type(tmp_path):
    src = _write_paste(tmp_path, "module-3.txt", "Module 3 transcript: pivots …")
    handler = CoursePlatformHandler(storage_dir=tmp_path / "storage")

    record = handler.ingest(f"course:{src}")

    assert record.source_type == "course_platform"
    assert record.source_id == compute_file_hash(src)
    assert record.title == "module-3"
    assert record.raw_text == "Module 3 transcript: pivots …"


def test_ingest_stores_paste_under_course_platform_storage(tmp_path):
    src = _write_paste(tmp_path, "lesson.txt", "x")
    handler = CoursePlatformHandler(storage_dir=tmp_path / "storage")

    record = handler.ingest(f"course:{src}")

    sha = record.source_id
    expected = tmp_path / "storage" / "course_platform" / sha[:2] / f"{sha}.txt"
    assert expected.exists()


def test_ingest_records_paths_in_metadata(tmp_path):
    src = _write_paste(tmp_path, "lesson.txt", "x")
    handler = CoursePlatformHandler(storage_dir=tmp_path / "storage")

    record = handler.ingest(f"course:{src}")

    assert record.metadata["source_path"] == str(src)
    assert "stored_path" in record.metadata


def test_ingest_rejects_unsupported_source(tmp_path):
    handler = CoursePlatformHandler(storage_dir=tmp_path / "storage")

    with pytest.raises(ValueError, match="cannot handle"):
        handler.ingest("discord:/path/paste.txt")


def test_ingest_rejects_missing_file(tmp_path):
    handler = CoursePlatformHandler(storage_dir=tmp_path / "storage")

    with pytest.raises(FileNotFoundError):
        handler.ingest("course:/does/not/exist.txt")
