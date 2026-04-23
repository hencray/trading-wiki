from datetime import datetime
from pathlib import Path
from typing import Any

from trading_wiki.core.audio import extract_audio_to_mp3
from trading_wiki.core.storage import store_file
from trading_wiki.core.transcribe import transcribe_audio
from trading_wiki.handlers.base import BaseHandler, ContentRecord

_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


class LocalVideoHandler(BaseHandler):
    """Ingest a local video file: store it, extract audio, transcribe."""

    def __init__(
        self,
        client: Any,
        storage_dir: Path,
        content_dir: Path,
    ) -> None:
        self._client = client
        self._storage_dir = storage_dir
        self._content_dir = content_dir

    def can_handle(self, source: str) -> bool:
        return Path(source).suffix.lower() in _VIDEO_EXTENSIONS

    def ingest(self, source: str) -> ContentRecord:
        if not self.can_handle(source):
            raise ValueError(f"cannot handle {source!r}")

        video_path = Path(source)
        sha, stored = store_file(video_path, "local_video", self._storage_dir)

        audio_path = self._content_dir / "local_video" / "audio" / f"{sha}.mp3"
        if not audio_path.exists():
            extract_audio_to_mp3(stored, audio_path)

        result = transcribe_audio(audio_path, self._client)

        return ContentRecord(
            source_type="local_video",
            source_id=sha,
            title=video_path.stem,
            created_at=datetime.fromtimestamp(video_path.stat().st_mtime),
            ingested_at=datetime.now(),
            raw_text=result.text,
            segments=result.segments,
            metadata={
                "source_path": str(video_path),
                "stored_path": str(stored),
                "audio_path": str(audio_path),
            },
        )
