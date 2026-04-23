from pathlib import Path

from openai import OpenAI

from trading_wiki.handlers.base import Segment, StrictModel


class TranscriptionResult(StrictModel):
    text: str
    segments: list[Segment]


def transcribe_audio(
    audio_path: Path,
    client: OpenAI,
    model: str = "whisper-1",
) -> TranscriptionResult:
    """Transcribe ``audio_path`` via the Whisper API.

    Returns the full text plus segment-level timestamps. The OpenAI
    client is injected so tests can pass a mock; production callers
    construct one from ``Settings.openai_api_key``.
    """
    with audio_path.open("rb") as f:
        response = client.audio.transcriptions.create(
            file=f,
            model=model,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
    raw_segments = response.segments or []
    segments = [
        Segment(
            seq=i,
            text=s.text,
            start_seconds=s.start,
            end_seconds=s.end,
        )
        for i, s in enumerate(raw_segments)
    ]
    return TranscriptionResult(text=response.text, segments=segments)
