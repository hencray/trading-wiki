from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL

from trading_wiki.handlers.base import StrictModel


class YoutubeMetadata(StrictModel):
    video_id: str
    title: str
    uploader: str
    upload_date: str  # YYYYMMDD as returned by yt-dlp


def fetch_youtube_metadata(
    url: str,
    ydl_factory: Any = YoutubeDL,
) -> YoutubeMetadata:
    """Fetch YouTube metadata without downloading the video.

    ``ydl_factory`` is injectable so tests can pass a mock; production
    callers use yt-dlp's real ``YoutubeDL`` class.
    """
    opts = {"quiet": True, "no_warnings": True}
    with ydl_factory(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return YoutubeMetadata(
        video_id=info["id"],
        title=info["title"],
        uploader=info.get("uploader", ""),
        upload_date=info.get("upload_date", ""),
    )


def download_youtube_audio(
    url: str,
    output_dir: Path,
    ydl_factory: Any = YoutubeDL,
) -> Path:
    """Download best audio for ``url`` as mp3 into ``output_dir``.

    Returns the path to the resulting ``{video_id}.mp3``. yt-dlp's
    FFmpegExtractAudio postprocessor handles the format conversion.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "32",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }
    with ydl_factory(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    return output_dir / f"{info['id']}.mp3"
