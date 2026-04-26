import shutil
import subprocess
from pathlib import Path

import pytest

from trading_wiki.core.audio import extract_audio_to_mp3

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


def test_extract_audio_to_mp3_produces_valid_mp3(tmp_path):
    video = tmp_path / "test.mp4"
    _make_silent_video(video)
    out = tmp_path / "out.mp3"

    extract_audio_to_mp3(video, out)

    assert out.exists()
    assert out.stat().st_size > 0
    with out.open("rb") as f:
        header = f.read(3)
    assert header[:2] == b"\xff\xfb" or header[:3] == b"ID3"


def test_extract_audio_raises_on_missing_input(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_audio_to_mp3(tmp_path / "missing.mp4", tmp_path / "out.mp3")


def test_extract_audio_raises_on_invalid_input(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_text("not a real video")
    with pytest.raises(subprocess.CalledProcessError):
        extract_audio_to_mp3(bad, tmp_path / "out.mp3")


def test_extract_audio_overwrites_existing_output(tmp_path):
    video = tmp_path / "test.mp4"
    _make_silent_video(video)
    out = tmp_path / "out.mp3"
    out.write_bytes(b"stale data that should be replaced")

    extract_audio_to_mp3(video, out)

    assert out.read_bytes() != b"stale data that should be replaced"


def test_extract_audio_bitrate_fits_long_videos(tmp_path):
    """Bitrate should be low enough that 3+ hours of audio fits under
    the Whisper 25 MiB limit. 16 kbps gives ~21.6 MB for 3 hours.
    """
    video = tmp_path / "test.mp4"
    _make_silent_video(video, duration=2.0)
    out = tmp_path / "out.mp3"
    extract_audio_to_mp3(video, out)

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=bit_rate",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(out),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    bitrate_bps = int(result.stdout.strip())
    # Expect ~16000 bps; allow generous range for codec frame variation.
    assert bitrate_bps <= 20000, f"bitrate {bitrate_bps} bps exceeds 20 kbps cap"
