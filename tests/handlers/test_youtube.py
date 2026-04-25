from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from trading_wiki.handlers.youtube import YoutubeHandler


def _make_ydl_factory_with_audio(info: dict[str, Any], audio_path: Path) -> MagicMock:
    factory = MagicMock()
    ydl = MagicMock()
    ydl.__enter__.return_value = ydl
    ydl.__exit__.return_value = None

    def extract_side_effect(url: str, download: bool = False) -> dict[str, Any]:
        if download:
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            audio_path.write_bytes(b"fake audio")
        return info

    ydl.extract_info.side_effect = extract_side_effect
    factory.return_value = ydl
    return factory


def _whisper_client(text: str = "", segments: list[SimpleNamespace] | None = None) -> MagicMock:
    client = MagicMock()
    client.audio.transcriptions.create.return_value = SimpleNamespace(
        text=text, segments=segments or []
    )
    return client


def _build_handler(
    tmp_path: Path, info: dict[str, Any], video_id: str
) -> tuple[YoutubeHandler, MagicMock]:
    audio_path = tmp_path / "content" / "youtube" / "audio" / f"{video_id}.mp3"
    factory = _make_ydl_factory_with_audio(info, audio_path)
    client = _whisper_client("hi", [SimpleNamespace(start=0.0, end=1.0, text="hi")])
    handler = YoutubeHandler(
        client=client,
        content_dir=tmp_path / "content",
        ydl_factory=factory,
    )
    return handler, factory


def test_can_handle_youtube_urls(tmp_path):
    handler, _ = _build_handler(tmp_path, {"id": "x"}, "x")
    assert handler.can_handle("https://www.youtube.com/watch?v=abc") is True
    assert handler.can_handle("https://youtube.com/watch?v=abc") is True
    assert handler.can_handle("https://youtu.be/abc") is True
    assert handler.can_handle("https://m.youtube.com/watch?v=abc") is True
    assert handler.can_handle("http://youtube.com/watch?v=abc") is True
    assert handler.can_handle("https://vimeo.com/123") is False
    assert handler.can_handle("/local/video.mp4") is False
    assert handler.can_handle("not a url") is False


def test_ingest_returns_content_record_with_video_id_as_source_id(tmp_path):
    info = {
        "id": "dQw4w9WgXcQ",
        "title": "Never Gonna Give You Up",
        "uploader": "Rick Astley",
        "upload_date": "20091025",
    }
    handler, _ = _build_handler(tmp_path, info, "dQw4w9WgXcQ")

    record = handler.ingest("https://youtube.com/watch?v=dQw4w9WgXcQ")

    assert record.source_type == "youtube"
    assert record.source_id == "dQw4w9WgXcQ"
    assert record.title == "Never Gonna Give You Up"
    assert record.author == "Rick Astley"
    assert record.raw_text == "hi"
    assert len(record.segments) == 1


def test_ingest_records_video_metadata(tmp_path):
    info = {
        "id": "abc",
        "title": "Lesson 1",
        "uploader": "v1 source",
        "upload_date": "20260101",
    }
    handler, _ = _build_handler(tmp_path, info, "abc")

    record = handler.ingest("https://youtube.com/watch?v=abc")

    assert record.metadata["url"] == "https://youtube.com/watch?v=abc"
    assert record.metadata["upload_date"] == "20260101"


def test_ingest_skips_download_when_audio_already_cached(tmp_path):
    info = {"id": "abc", "title": "t", "uploader": "u", "upload_date": "20260101"}
    audio_path = tmp_path / "content" / "youtube" / "audio" / "abc.mp3"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"cached audio")

    handler, factory = _build_handler(tmp_path, info, "abc")
    handler.ingest("https://youtube.com/watch?v=abc")

    extract_calls = factory.return_value.extract_info.call_args_list
    download_kwargs = [c.kwargs.get("download", False) for c in extract_calls]
    assert True not in download_kwargs


def test_ingest_rejects_non_youtube_url(tmp_path):
    handler, _ = _build_handler(tmp_path, {"id": "x"}, "x")
    with pytest.raises(ValueError, match="cannot handle"):
        handler.ingest("https://vimeo.com/123")
