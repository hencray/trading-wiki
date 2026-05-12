"""Phase 2C v2 — Chart extraction from video scene-change frames.

Uses ffmpeg's `scene` filter to sample frames at visual transitions (~20-50
frames per 60-min video typically), then calls Sonnet 4.6 vision API on
each to classify (chart or not) and extract ticker / timeframe / annotations
when present. Frame images are saved under gitignored `storage/charts/`,
keyed by sha256(image bytes). De-dupe is on the hash.

v1 (PDF/EPUB/Discord image sources) shares the same charts table + Sonnet
vision classifier; it ships when image-source content is ingested.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import structlog
from pydantic import Field

from trading_wiki.core.secrets import Settings
from trading_wiki.handlers.base import StrictModel

_log = structlog.get_logger(__name__)

CHART_VISION_MODEL = "claude-sonnet-4-6"
PROMPT_VERSION_PASS2C_CHART = "pass2c-chart-v1"
CHARTS_STORAGE_DIR = Path("storage/charts")

Confidence = Literal["low", "medium", "high"]


class ChartClassification(StrictModel):
    """The vision-model output schema (per frame)."""

    is_chart: bool
    ticker: str | None = Field(default=None, max_length=20)
    timeframe: str | None = Field(default=None, max_length=50)
    date_range: str | None = Field(default=None, max_length=80)
    indicators: list[str] = Field(default_factory=list, max_length=15)
    annotations: list[str] = Field(default_factory=list, max_length=20)
    pattern_description: str | None = Field(default=None, max_length=400)
    confidence: Confidence


@dataclass
class FrameResult:
    timestamp_seconds: float
    image_path: Path
    image_hash: str
    classification: ChartClassification
    cost_usd: float


@dataclass
class Pass2CSummary:
    frames_extracted: int = 0
    frames_classified: int = 0
    charts_found: int = 0
    non_charts: int = 0
    total_cost_usd: float = 0.0
    failed_frames: list[tuple[str, str]] = field(default_factory=list)


def _ffmpeg_scene_change_timestamps(
    video_path: Path, *, threshold: float = 0.4, max_frames: int | None = None
) -> list[float]:
    """Return scene-change timestamps (in seconds) using ffmpeg's `scene`
    filter. Higher ``threshold`` = fewer (more distinct) scene changes."""
    cmd = [
        "ffmpeg",
        "-i",
        str(video_path),
        "-filter_complex",
        f"select='gt(scene,{threshold})',showinfo",
        "-vsync",
        "vfr",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    # showinfo writes to stderr lines like:
    #   [Parsed_showinfo_1 @ 0x...] n: 0 pts: 12345 pts_time:1.234 ...
    timestamps: list[float] = []
    for line in proc.stderr.splitlines():
        if "pts_time:" not in line:
            continue
        try:
            ts_part = line.split("pts_time:")[1].split()[0]
            timestamps.append(float(ts_part))
        except (IndexError, ValueError):
            continue
    timestamps.sort()
    if max_frames is not None and len(timestamps) > max_frames:
        # Sample evenly across the timeline rather than taking the first N
        step = len(timestamps) / max_frames
        sampled = [timestamps[int(i * step)] for i in range(max_frames)]
        timestamps = sampled
    return timestamps


def _extract_frame_at(video_path: Path, *, timestamp_seconds: float, out_path: Path) -> None:
    """Use ffmpeg to grab a single JPEG frame at the given timestamp."""
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{timestamp_seconds:.3f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        "3",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError(
            f"ffmpeg failed to extract frame at {timestamp_seconds}s: {proc.stderr[:300]}"
        )


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _classify_frame_with_vision(
    *, image_bytes: bytes, anthropic_client: Any
) -> tuple[ChartClassification, float]:
    """Call Sonnet 4.6 with the frame image and a chart-classification tool
    schema. Returns the parsed classification + USD cost estimate."""
    tool_schema = {
        "name": "submit_chart_classification",
        "description": "Submit a classification of whether the image is a trading chart.",
        "input_schema": ChartClassification.model_json_schema(),
    }
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    system_prompt = (
        "You are classifying a single frame from a trading-education video. "
        "Decide whether the frame shows a stock/futures/crypto chart. If yes, "
        "extract any visible ticker symbol, timeframe (e.g. 60-min, daily), "
        "approximate date range, indicators shown (Bollinger Bands, SMAs, RSI, "
        "etc.), and any visible annotations (arrows, entry/exit labels, "
        "support/resistance lines). If the image is NOT a chart (slide, talking "
        "head, blank, watermark, etc.), set is_chart=false and leave the rest empty."
    )
    response = anthropic_client.messages.create(
        model=CHART_VISION_MODEL,
        max_tokens=2048,
        system=system_prompt,
        tools=[tool_schema],
        tool_choice={"type": "tool", "name": "submit_chart_classification"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": "Classify this frame."},
                ],
            }
        ],
    )
    tool_block = next(b for b in response.content if getattr(b, "type", None) == "tool_use")
    classification = ChartClassification(**tool_block.input)
    usage = response.usage
    input_tokens = int(getattr(usage, "input_tokens", 0))
    output_tokens = int(getattr(usage, "output_tokens", 0))
    # Sonnet 4.6: $3/MTok input, $15/MTok output (image tokens count as input)
    cost = (input_tokens / 1_000_000) * 3.0 + (output_tokens / 1_000_000) * 15.0
    return classification, cost


def _save_frame_to_storage(*, frame_path: Path, image_hash: str) -> Path:
    """Move the frame from tempdir into the gitignored storage/charts/ tree
    keyed by hash. Returns the final on-disk path."""
    CHARTS_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    final_path = CHARTS_STORAGE_DIR / f"{image_hash}.jpg"
    if not final_path.exists():
        final_path.write_bytes(frame_path.read_bytes())
    return final_path


def _persist_chart(
    db_path: Path,
    *,
    source_content_id: int,
    source_chunk_id: int | None,
    frame: FrameResult,
    prompt_version: str,
) -> bool:
    """Insert a chart row. Returns True if inserted, False if duplicate
    (UNIQUE on image_hash + prompt_version)."""
    now = datetime.now().isoformat(timespec="seconds")
    c = frame.classification
    with sqlite3.connect(db_path) as conn:
        try:
            conn.execute(
                """
                INSERT INTO charts
                (source_content_id, source_chunk_id, source_timestamp_seconds,
                 image_path, image_hash, is_chart, ticker, timeframe, date_range,
                 indicators, annotations, pattern_description, confidence,
                 prompt_version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_content_id,
                    source_chunk_id,
                    frame.timestamp_seconds,
                    str(frame.image_path),
                    frame.image_hash,
                    int(c.is_chart),
                    c.ticker,
                    c.timeframe,
                    c.date_range,
                    json.dumps(c.indicators),
                    json.dumps(c.annotations),
                    c.pattern_description,
                    c.confidence,
                    prompt_version,
                    now,
                ),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def _find_chunk_for_timestamp(
    db_path: Path, *, content_id: int, timestamp_seconds: float
) -> int | None:
    """Return the Pass-1 chunk id whose [start_seconds, end_seconds] window
    contains ``timestamp_seconds``, or ``None`` if no chunk matches."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT id FROM chunks
            WHERE content_id = ?
              AND start_seconds <= ?
              AND end_seconds >= ?
            ORDER BY seq
            LIMIT 1
            """,
            (content_id, timestamp_seconds, timestamp_seconds),
        ).fetchone()
    return int(row[0]) if row else None


def extract_charts_for_content(
    *,
    content_id: int,
    db_path: Path | None = None,
    anthropic_client: Any,
    max_frames: int | None = None,
    scene_threshold: float = 0.4,
    prompt_version: str = PROMPT_VERSION_PASS2C_CHART,
) -> Pass2CSummary:
    """Extract scene-change frames from a video, classify each via Sonnet 4.6
    vision, and persist findings to the `charts` table."""
    db_path = Path(db_path) if db_path is not None else Settings().db_path
    summary = Pass2CSummary()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, source_type, metadata FROM content WHERE id = ?",
            (content_id,),
        ).fetchone()
    if row is None:
        raise LookupError(f"unknown content_id={content_id}")
    if row["source_type"] != "local_video":
        raise ValueError(
            f"content_id={content_id} is source_type={row['source_type']!r}; "
            "Chart v2 only handles local_video. (Chart v1 for image sources is deferred.)"
        )
    metadata = json.loads(row["metadata"])
    stored_path = metadata.get("stored_path")
    if stored_path is None:
        raise RuntimeError(f"content_id={content_id} has no stored_path in metadata")
    video_path = Path(stored_path)
    if not video_path.exists():
        raise FileNotFoundError(f"video file missing: {video_path}")

    _log.info(
        "pass2c.scene_detect.start",
        content_id=content_id,
        max_frames=max_frames,
        threshold=scene_threshold,
    )
    timestamps = _ffmpeg_scene_change_timestamps(
        video_path, threshold=scene_threshold, max_frames=max_frames
    )
    summary.frames_extracted = len(timestamps)
    _log.info(
        "pass2c.scene_detect.ok",
        content_id=content_id,
        frame_count=len(timestamps),
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for i, ts in enumerate(timestamps):
            tmp_frame = tmpdir / f"frame_{i:04d}.jpg"
            try:
                _extract_frame_at(video_path, timestamp_seconds=ts, out_path=tmp_frame)
                image_bytes = tmp_frame.read_bytes()
                image_hash = hashlib.sha256(image_bytes).hexdigest()
                # Save to long-term storage keyed by hash.
                final_path = _save_frame_to_storage(frame_path=tmp_frame, image_hash=image_hash)
                classification, cost = _classify_frame_with_vision(
                    image_bytes=image_bytes, anthropic_client=anthropic_client
                )
                summary.frames_classified += 1
                summary.total_cost_usd += cost
                if classification.is_chart:
                    summary.charts_found += 1
                else:
                    summary.non_charts += 1

                frame_result = FrameResult(
                    timestamp_seconds=ts,
                    image_path=final_path,
                    image_hash=image_hash,
                    classification=classification,
                    cost_usd=cost,
                )
                chunk_id = _find_chunk_for_timestamp(
                    db_path, content_id=content_id, timestamp_seconds=ts
                )
                _persist_chart(
                    db_path,
                    source_content_id=content_id,
                    source_chunk_id=chunk_id,
                    frame=frame_result,
                    prompt_version=prompt_version,
                )
            except Exception as e:
                summary.failed_frames.append((f"frame_{i}_t{ts:.2f}", repr(e)))
                _log.warning(
                    "pass2c.frame.failed",
                    content_id=content_id,
                    timestamp=ts,
                    error=repr(e),
                )

    _log.info(
        "pass2c.extract.ok",
        content_id=content_id,
        frames_extracted=summary.frames_extracted,
        frames_classified=summary.frames_classified,
        charts_found=summary.charts_found,
        non_charts=summary.non_charts,
        failed_count=len(summary.failed_frames),
        total_cost_usd=summary.total_cost_usd,
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m trading_wiki.pass2c.chart_extractor",
        description="Phase 2C v2 — extract + classify chart frames from one video.",
    )
    parser.add_argument("--content-id", type=int, required=True)
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Cap the number of scene-change frames classified (cost control).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.4,
        help="ffmpeg scene-change threshold (higher = fewer scenes).",
    )
    args = parser.parse_args(argv)

    settings = Settings()
    if settings.anthropic_api_key is None:
        raise SystemExit("ANTHROPIC_API_KEY required for vision classification.")

    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key.get_secret_value())

    summary = extract_charts_for_content(
        content_id=args.content_id,
        anthropic_client=client,
        max_frames=args.max_frames,
        scene_threshold=args.threshold,
    )
    print(
        f"Pass 2C for content_id={args.content_id}: "
        f"{summary.frames_extracted} scene frames, "
        f"{summary.frames_classified} classified, "
        f"{summary.charts_found} charts / {summary.non_charts} non-charts; "
        f"{len(summary.failed_frames)} failed; "
        f"cost ≈ ${summary.total_cost_usd:.4f}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
