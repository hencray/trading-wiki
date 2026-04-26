"""Phase 2A v0.1 — Pass 1 (chunk + classify).

See docs/superpowers/specs/2026-04-25-phase-2a-pass1-design.md.
"""

from itertools import pairwise
from pathlib import Path
from typing import Literal

import structlog
from pydantic import Field

from trading_wiki.config import (
    MODEL_PASS1,
    PROMPT_PASS1_PATH,
    PROMPT_VERSION_PASS1,
)
from trading_wiki.core.db import (
    content_exists,
    load_chunks_for_version,
    load_segments_for_content_id,
    save_chunks,
)
from trading_wiki.core.llm import UsageRecord, call_structured
from trading_wiki.core.secrets import Settings
from trading_wiki.handlers.base import Segment, StrictModel

_log = structlog.get_logger(__name__)

Label = Literal[
    "strategy",
    "concept",
    "example",
    "psychology",
    "market_commentary",
    "qa",
    "noise",
]
Confidence = Literal["low", "medium", "high"]


class Pass1Chunk(StrictModel):
    seq: int
    start_seg_seq: int
    end_seg_seq: int
    label: Label
    confidence: Confidence
    summary: str = Field(max_length=120)


class Pass1Output(StrictModel):
    chunks: list[Pass1Chunk]


class CoverageError(ValueError):
    """Raised when Pass 1 output does not cover the transcript correctly."""


def validate_coverage(output: Pass1Output, *, segment_count: int) -> None:
    """Validate chunks cover [0, segment_count) end-to-end with no gaps/overlaps.

    Spec §5.3.
    """
    chunks = output.chunks
    if not chunks:
        raise CoverageError("chunks list is empty")

    for i, c in enumerate(chunks):
        if c.seq != i:
            raise CoverageError(
                f"chunk at index {i} has seq={c.seq}; expected {i} (sequential, 0-indexed)"
            )
        if c.start_seg_seq > c.end_seg_seq:
            raise CoverageError(
                f"chunk {i}: start_seg_seq={c.start_seg_seq} > end_seg_seq={c.end_seg_seq}"
            )

    if chunks[0].start_seg_seq != 0:
        raise CoverageError(f"first chunk must start at segment 0, got {chunks[0].start_seg_seq}")
    if chunks[-1].end_seg_seq != segment_count - 1:
        raise CoverageError(
            f"last chunk must cover the last segment ({segment_count - 1}); "
            f"got end_seg_seq={chunks[-1].end_seg_seq}"
        )
    for prev, curr in pairwise(chunks):
        expected_start = prev.end_seg_seq + 1
        if curr.start_seg_seq < expected_start:
            raise CoverageError(
                f"overlap between chunk {prev.seq} (ends at seg {prev.end_seg_seq}) "
                f"and chunk {curr.seq} (starts at seg {curr.start_seg_seq})"
            )
        if curr.start_seg_seq > expected_start:
            raise CoverageError(
                f"gap between chunk {prev.seq} (ends at seg {prev.end_seg_seq}) "
                f"and chunk {curr.seq} (starts at seg {curr.start_seg_seq}); "
                f"missing segments {expected_start}..{curr.start_seg_seq - 1}"
            )


def build_transcript_text(segments: list[Segment]) -> str:
    """Format segments as ``[seg N] (start.s-end.s) text`` lines for the LLM prompt."""
    lines: list[str] = []
    for s in segments:
        if s.start_seconds is not None and s.end_seconds is not None:
            timing = f"({s.start_seconds:.1f}s-{s.end_seconds:.1f}s) "
        else:
            timing = ""
        lines.append(f"[seg {s.seq}] {timing}{s.text}")
    return "\n".join(lines)


def extract(
    *,
    content_id: int,
    db_path: Path | None = None,
) -> list[dict[str, object]]:
    """Run Pass 1 on a single content_id.

    Returns the chunk rows that were written (or were already present, if
    idempotency short-circuits the call).

    Spec §4 data flow.
    """
    db_path = Path(db_path) if db_path is not None else Settings().db_path

    if not content_exists(db_path, content_id=content_id):
        raise LookupError(f"unknown content_id={content_id}")

    existing = load_chunks_for_version(
        db_path, content_id=content_id, prompt_version=PROMPT_VERSION_PASS1
    )
    if existing:
        _log.info(
            "pass1.idempotent_skip",
            content_id=content_id,
            prompt_version=PROMPT_VERSION_PASS1,
            existing_count=len(existing),
        )
        return existing

    segments = load_segments_for_content_id(db_path, content_id=content_id)
    segment_count = len(segments)
    if segment_count == 0:
        raise LookupError(f"content_id={content_id} has no segments")

    transcript = build_transcript_text(segments)
    system_prompt = PROMPT_PASS1_PATH.read_text(encoding="utf-8")

    output, usage, history = call_structured(
        model=MODEL_PASS1,
        system=system_prompt,
        messages=[{"role": "user", "content": transcript}],
        schema=Pass1Output,
    )

    try:
        validate_coverage(output, segment_count=segment_count)
    except CoverageError as e:
        _log.warning(
            "pass1.coverage_retry",
            content_id=content_id,
            error=str(e),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
        history.append(
            {
                "role": "user",
                "content": (
                    f"Coverage validation failed: {e}. "
                    f"Please regenerate the chunks correctly covering all "
                    f"{segment_count} segments (indices 0..{segment_count - 1}) "
                    "without gaps or overlaps."
                ),
            }
        )
        output, retry_usage, _ = call_structured(
            model=MODEL_PASS1,
            system=system_prompt,
            messages=history,
            schema=Pass1Output,
        )
        usage = UsageRecord(
            model=usage.model,
            input_tokens=usage.input_tokens + retry_usage.input_tokens,
            output_tokens=usage.output_tokens + retry_usage.output_tokens,
            cost_estimate_usd=usage.cost_estimate_usd + retry_usage.cost_estimate_usd,
        )
        validate_coverage(output, segment_count=segment_count)

    save_chunks(
        db_path,
        content_id=content_id,
        prompt_version=PROMPT_VERSION_PASS1,
        output=output,
    )
    _log.info(
        "pass1.extract.ok",
        content_id=content_id,
        prompt_version=PROMPT_VERSION_PASS1,
        chunk_count=len(output.chunks),
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_estimate_usd=usage.cost_estimate_usd,
    )
    return load_chunks_for_version(
        db_path, content_id=content_id, prompt_version=PROMPT_VERSION_PASS1
    )
