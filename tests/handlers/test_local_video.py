import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from trading_wiki.core.storage import compute_file_hash
from trading_wiki.handlers.local_video import LocalVideoHandler

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _make_silent_video(path: Path, duration: float = 0.5) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=64x64:d={duration}",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=8000:d={duration}",
            "-shortest",
            "-y",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _whisper_response(text: str, segments: list[SimpleNamespace]) -> SimpleNamespace:
    return SimpleNamespace(text=text, segments=segments)


def _build_handler(
    tmp_path: Path, response: SimpleNamespace
) -> tuple[LocalVideoHandler, MagicMock]:
    client = MagicMock()
    client.audio.transcriptions.create.return_value = response
    handler = LocalVideoHandler(
        client=client,
        storage_dir=tmp_path / "storage",
        content_dir=tmp_path / "content",
    )
    return handler, client


def test_can_handle_video_extensions(tmp_path):
    handler, _ = _build_handler(tmp_path, _whisper_response("", []))
    assert handler.can_handle("/p/lesson.mp4") is True
    assert handler.can_handle("/p/lesson.MP4") is True
    assert handler.can_handle("/p/lesson.mov") is True
    assert handler.can_handle("/p/lesson.mkv") is True
    assert handler.can_handle("/p/lesson.webm") is True
    assert handler.can_handle("/p/lesson.txt") is False
    assert handler.can_handle("/p/lesson") is False


def test_ingest_returns_content_record_with_hash_as_source_id(tmp_path):
    video = tmp_path / "lesson.mp4"
    _make_silent_video(video)
    handler, _ = _build_handler(
        tmp_path,
        _whisper_response("hi", [SimpleNamespace(start=0.0, end=0.5, text="hi")]),
    )

    record = handler.ingest(str(video))

    assert record.source_type == "local_video"
    assert record.source_id == compute_file_hash(video)
    assert record.title == "lesson"
    assert record.raw_text == "hi"
    assert len(record.segments) == 1
    assert record.segments[0].text == "hi"


def test_ingest_stores_source_in_content_addressed_location(tmp_path):
    video = tmp_path / "lesson.mp4"
    _make_silent_video(video)
    handler, _ = _build_handler(tmp_path, _whisper_response("", []))

    record = handler.ingest(str(video))

    sha = record.source_id
    expected_stored = tmp_path / "storage" / "local_video" / sha[:2] / f"{sha}.mp4"
    assert expected_stored.exists()


def test_ingest_extracts_audio_to_content_dir(tmp_path):
    video = tmp_path / "lesson.mp4"
    _make_silent_video(video)
    handler, _ = _build_handler(tmp_path, _whisper_response("", []))

    record = handler.ingest(str(video))

    sha = record.source_id
    audio = tmp_path / "content" / "local_video" / "audio" / f"{sha}.mp3"
    assert audio.exists()
    assert audio.stat().st_size > 0


def test_ingest_uses_existing_audio_when_already_extracted(tmp_path):
    video = tmp_path / "lesson.mp4"
    _make_silent_video(video)
    handler, _ = _build_handler(tmp_path, _whisper_response("", []))

    handler.ingest(str(video))
    sha = compute_file_hash(video)
    audio = tmp_path / "content" / "local_video" / "audio" / f"{sha}.mp3"
    audio.write_bytes(b"sentinel-bytes-for-skip-test")

    handler.ingest(str(video))
    assert audio.read_bytes() == b"sentinel-bytes-for-skip-test"


def test_ingest_records_paths_in_metadata(tmp_path):
    video = tmp_path / "lesson.mp4"
    _make_silent_video(video)
    handler, _ = _build_handler(tmp_path, _whisper_response("", []))

    record = handler.ingest(str(video))

    assert record.metadata["source_path"] == str(video)
    assert "stored_path" in record.metadata
    assert "audio_path" in record.metadata


def test_ingest_rejects_unsupported_source(tmp_path):
    txt = tmp_path / "notes.txt"
    txt.write_text("hello")
    handler, _ = _build_handler(tmp_path, _whisper_response("", []))

    with pytest.raises(ValueError, match="cannot handle"):
        handler.ingest(str(txt))
