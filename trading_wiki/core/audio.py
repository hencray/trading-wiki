import subprocess
from pathlib import Path


def extract_audio_to_mp3(video_path: Path, output_path: Path) -> None:
    """Extract audio from ``video_path`` as a Whisper-friendly mp3.

    Output is mono 16 kHz at 16 kbps — small enough for ~3.5 hours of audio
    to stay under the Whisper API's 25 MiB upload limit. 16 kbps is fine for
    speech transcription (Whisper is robust to compressed speech).
    """
    if not video_path.exists():
        raise FileNotFoundError(video_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "libmp3lame",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-b:a",
            "16k",
            "-y",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
