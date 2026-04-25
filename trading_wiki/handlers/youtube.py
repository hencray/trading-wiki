import re
from datetime import datetime
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL

from trading_wiki.core.transcribe import transcribe_audio
from trading_wiki.core.youtube import download_youtube_audio, fetch_youtube_metadata
from trading_wiki.handlers.base import BaseHandler, ContentRecord

_YOUTUBE_URL_PATTERN = re.compile(
    r"^https?://(www\.|m\.)?(youtube\.com/watch\?v=|youtu\.be/)[A-Za-z0-9_-]+",
    re.IGNORECASE,
)


class YoutubeHandler(BaseHandler):
    """Ingest a YouTube URL: fetch metadata, download audio, transcribe."""

    def __init__(
        self,
        client: Any,
        content_dir: Path,
        ydl_factory: Any = YoutubeDL,
    ) -> None:
        self._client = client
        self._content_dir = content_dir
        self._ydl_factory = ydl_factory

    def can_handle(self, source: str) -> bool:
        return bool(_YOUTUBE_URL_PATTERN.match(source))

    def ingest(self, source: str) -> ContentRecord:
        if not self.can_handle(source):
            raise ValueError(f"cannot handle {source!r}")

        meta = fetch_youtube_metadata(source, self._ydl_factory)
        audio_dir = self._content_dir / "youtube" / "audio"
        audio_path = audio_dir / f"{meta.video_id}.mp3"
        if not audio_path.exists():
            download_youtube_audio(source, audio_dir, self._ydl_factory)

        result = transcribe_audio(audio_path, self._client)

        return ContentRecord(
            source_type="youtube",
            source_id=meta.video_id,
            title=meta.title,
            author=meta.uploader or None,
            created_at=_parse_upload_date(meta.upload_date),
            ingested_at=datetime.now(),
            raw_text=result.text,
            segments=result.segments,
            metadata={
                "url": source,
                "upload_date": meta.upload_date,
                "audio_path": str(audio_path),
            },
        )


def _parse_upload_date(date_str: str) -> datetime:
    """Parse yt-dlp's ``YYYYMMDD`` upload date; fall back to now if missing."""
    if len(date_str) == 8 and date_str.isdigit():
        return datetime.strptime(date_str, "%Y%m%d")
    return datetime.now()
