from typing import Any
from unittest.mock import MagicMock

from trading_wiki.core.youtube import (
    YoutubeMetadata,
    download_youtube_audio,
    fetch_youtube_metadata,
)


def _make_ydl_factory(info: dict[str, Any]) -> MagicMock:
    factory = MagicMock()
    ydl = MagicMock()
    ydl.__enter__.return_value = ydl
    ydl.__exit__.return_value = None
    ydl.extract_info.return_value = info
    factory.return_value = ydl
    return factory


def test_fetch_youtube_metadata_returns_typed_model():
    factory = _make_ydl_factory(
        {
            "id": "dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "uploader": "Rick Astley",
            "upload_date": "20091025",
        }
    )

    meta = fetch_youtube_metadata("https://youtube.com/watch?v=dQw4w9WgXcQ", ydl_factory=factory)

    assert isinstance(meta, YoutubeMetadata)
    assert meta.video_id == "dQw4w9WgXcQ"
    assert meta.title == "Never Gonna Give You Up"
    assert meta.uploader == "Rick Astley"
    assert meta.upload_date == "20091025"


def test_fetch_youtube_metadata_does_not_download():
    factory = _make_ydl_factory(
        {"id": "x", "title": "t", "uploader": "u", "upload_date": "20260101"}
    )

    fetch_youtube_metadata("https://youtube.com/watch?v=x", ydl_factory=factory)

    ydl = factory.return_value
    ydl.extract_info.assert_called_once()
    assert ydl.extract_info.call_args.kwargs.get("download") is False


def test_download_youtube_audio_uses_mp3_postprocessor(tmp_path):
    factory = _make_ydl_factory({"id": "abc"})

    download_youtube_audio("https://youtube.com/watch?v=abc", tmp_path, ydl_factory=factory)

    opts = factory.call_args.args[0]
    assert opts["format"].startswith("bestaudio")
    assert opts["postprocessors"][0]["preferredcodec"] == "mp3"
    assert opts["outtmpl"].startswith(str(tmp_path))


def test_download_youtube_audio_returns_mp3_path(tmp_path):
    factory = _make_ydl_factory({"id": "xyz789"})

    path = download_youtube_audio(
        "https://youtube.com/watch?v=xyz789", tmp_path, ydl_factory=factory
    )

    assert path == tmp_path / "xyz789.mp3"


def test_download_youtube_audio_creates_output_dir(tmp_path):
    factory = _make_ydl_factory({"id": "abc"})
    target = tmp_path / "nested" / "youtube" / "audio"

    download_youtube_audio("https://youtube.com/watch?v=abc", target, ydl_factory=factory)

    assert target.exists()
    assert target.is_dir()
