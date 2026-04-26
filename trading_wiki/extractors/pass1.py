"""Phase 2A v0.1 — Pass 1 (chunk + classify).

See docs/superpowers/specs/2026-04-25-phase-2a-pass1-design.md.
"""

from typing import Literal

from pydantic import Field

from trading_wiki.handlers.base import StrictModel

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
