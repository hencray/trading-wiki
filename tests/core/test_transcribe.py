from types import SimpleNamespace
from unittest.mock import MagicMock

from trading_wiki.core.transcribe import transcribe_audio


def _make_client(text: str, segments: list[SimpleNamespace]) -> MagicMock:
    client = MagicMock()
    client.audio.transcriptions.create.return_value = SimpleNamespace(
        text=text,
        segments=segments,
    )
    return client


def test_transcribe_audio_returns_text_and_segments(tmp_path):
    audio = tmp_path / "test.mp3"
    audio.write_bytes(b"fake audio bytes")
    client = _make_client(
        "hello world",
        [
            SimpleNamespace(start=0.0, end=1.5, text="hello"),
            SimpleNamespace(start=1.5, end=3.0, text=" world"),
        ],
    )

    result = transcribe_audio(audio, client)

    assert result.text == "hello world"
    assert len(result.segments) == 2
    assert result.segments[0].seq == 0
    assert result.segments[0].text == "hello"
    assert result.segments[0].start_seconds == 0.0
    assert result.segments[0].end_seconds == 1.5
    assert result.segments[1].seq == 1
    assert result.segments[1].text == " world"


def test_transcribe_audio_uses_verbose_json_with_segment_timestamps(tmp_path):
    audio = tmp_path / "test.mp3"
    audio.write_bytes(b"fake")
    client = _make_client("x", [])

    transcribe_audio(audio, client)

    kwargs = client.audio.transcriptions.create.call_args.kwargs
    assert kwargs["model"] == "whisper-1"
    assert kwargs["response_format"] == "verbose_json"
    assert kwargs["timestamp_granularities"] == ["segment"]


def test_transcribe_audio_handles_empty_segments(tmp_path):
    audio = tmp_path / "silent.mp3"
    audio.write_bytes(b"silence")
    client = _make_client("", [])

    result = transcribe_audio(audio, client)

    assert result.text == ""
    assert result.segments == []
