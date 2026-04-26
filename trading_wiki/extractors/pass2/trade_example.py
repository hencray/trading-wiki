"""Phase 2A v0.2 — Pass 2 TradeExample extractor.

See docs/superpowers/specs/2026-04-25-phase-2a-pass2-design.md.
"""

from typing import Literal

from pydantic import Field

from trading_wiki.handlers.base import StrictModel

Direction = Literal["long", "short"]
InstrumentType = Literal["stock", "option", "future", "crypto", "other"]
OutcomeClassification = Literal["won", "lost", "scratch", "unknown"]
Confidence = Literal["low", "medium", "high"]


class TradeExample(StrictModel):
    ticker: str = Field(min_length=1, max_length=20)
    direction: Direction
    instrument_type: InstrumentType
    trade_date: str | None = None
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    exit_price: float | None = None
    entry_description: str = Field(min_length=1, max_length=500)
    exit_description: str = Field(min_length=1, max_length=500)
    outcome_text: str = Field(min_length=1, max_length=200)
    outcome_classification: OutcomeClassification | None = None
    lessons: str | None = Field(default=None, max_length=500)
    confidence: Confidence


class TradeExampleOutput(StrictModel):
    entities: list[TradeExample]
