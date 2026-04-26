"""Phase 2A v0.2 — Pass 2 Concept extractor.

See docs/superpowers/specs/2026-04-25-phase-2a-pass2-design.md.
"""

from typing import Literal

from pydantic import Field

from trading_wiki.handlers.base import StrictModel

Confidence = Literal["low", "medium", "high"]


class Concept(StrictModel):
    term: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=10, max_length=400)
    related_terms: list[str] = Field(default_factory=list, max_length=15)
    confidence: Confidence


class ConceptOutput(StrictModel):
    entities: list[Concept]
