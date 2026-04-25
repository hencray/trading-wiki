from pathlib import Path

import pytest

from trading_wiki.core.storage import compute_file_hash
from trading_wiki.handlers.discord import DiscordHandler


def _write_paste(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_can_handle_discord_prefix(tmp_path):
    handler = DiscordHandler(storage_dir=tmp_path / "storage")
    assert handler.can_handle("discord:/abs/path/paste.txt") is True
    assert handler.can_handle("discord:relative/paste.txt") is True
    assert handler.can_handle("discord:") is True


def test_does_not_handle_other_sources(tmp_path):
    handler = DiscordHandler(storage_dir=tmp_path / "storage")
    assert handler.can_handle("/local/video.mp4") is False
    assert handler.can_handle("https://youtube.com/watch?v=abc") is False
    assert handler.can_handle("course:/path/notes.txt") is False
    assert handler.can_handle("notes.txt") is False


def test_ingest_returns_content_record_with_discord_source_type(tmp_path):
    src = _write_paste(tmp_path, "pivots.txt", "[Author] watch the close")
    handler = DiscordHandler(storage_dir=tmp_path / "storage")

    record = handler.ingest(f"discord:{src}")

    assert record.source_type == "discord"
    assert record.source_id == compute_file_hash(src)
    assert record.title == "pivots"
    assert record.raw_text == "[Author] watch the close"


def test_ingest_stores_paste_under_discord_storage(tmp_path):
    src = _write_paste(tmp_path, "paste.txt", "hello")
    handler = DiscordHandler(storage_dir=tmp_path / "storage")

    record = handler.ingest(f"discord:{src}")

    sha = record.source_id
    expected = tmp_path / "storage" / "discord" / sha[:2] / f"{sha}.txt"
    assert expected.exists()


def test_ingest_records_paths_in_metadata(tmp_path):
    src = _write_paste(tmp_path, "paste.txt", "hello")
    handler = DiscordHandler(storage_dir=tmp_path / "storage")

    record = handler.ingest(f"discord:{src}")

    assert record.metadata["source_path"] == str(src)
    assert "stored_path" in record.metadata


def test_ingest_rejects_unsupported_source(tmp_path):
    handler = DiscordHandler(storage_dir=tmp_path / "storage")

    with pytest.raises(ValueError, match="cannot handle"):
        handler.ingest("/local/video.mp4")


def test_ingest_rejects_missing_file(tmp_path):
    handler = DiscordHandler(storage_dir=tmp_path / "storage")

    with pytest.raises(FileNotFoundError):
        handler.ingest("discord:/does/not/exist.txt")
