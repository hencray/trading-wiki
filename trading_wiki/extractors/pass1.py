"""Phase 2A v0.1 — Pass 1 (chunk + classify).

See docs/superpowers/specs/2026-04-25-phase-2a-pass1-design.md.
"""

from itertools import pairwise
from typing import Literal

from pydantic import Field

from trading_wiki.handlers.base import Segment, StrictModel

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
