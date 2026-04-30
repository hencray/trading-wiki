"""Phase 2A v0.2 — Pass 2 TradeExample extractor."""

from pathlib import Path
from typing import Literal

import structlog
from pydantic import Field

from trading_wiki.config import (
    MODEL_PASS2,
    PROMPT_PASS2_TRADE_EXAMPLE_PATH,
    PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
)
from trading_wiki.core.db import (
    load_chunk_by_id,
    load_trade_examples_for_version,
    pass2_run_exists,
    record_pass2_run,
    save_trade_examples,
)
from trading_wiki.core.llm import UsageRecord, call_structured
from trading_wiki.core.secrets import Settings
from trading_wiki.handlers.base import StrictModel

_log = structlog.get_logger(__name__)

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


def _zero_usage() -> UsageRecord:
    return UsageRecord(
        model=MODEL_PASS2,
        input_tokens=0,
        output_tokens=0,
        cost_estimate_usd=0.0,
    )


def extract_trade_examples_for_chunk(
    *,
    chunk_id: int,
    db_path: Path | None = None,
) -> tuple[list[TradeExample], UsageRecord]:
    """Run the TradeExample extractor against one chunk_id.

    Returns ``(entities, usage)``. On idempotency hit, ``entities`` is rebuilt
    from the stored rows and ``usage`` is a zero-cost record (no API call).

    Spec §5.4 data flow.
    """
    db_path = Path(db_path) if db_path is not None else Settings().db_path

    chunk = load_chunk_by_id(db_path, chunk_id=chunk_id)
    if chunk is None:
        raise LookupError(f"unknown chunk_id={chunk_id}")

    if pass2_run_exists(
        db_path,
        source_chunk_id=chunk_id,
        extractor="trade_example",
        prompt_version=PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
    ):
        existing = load_trade_examples_for_version(
            db_path,
            source_chunk_id=chunk_id,
            prompt_version=PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
        )
        _log.info(
            "pass2.trade_example.idempotent_skip",
            chunk_id=chunk_id,
            prompt_version=PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
            existing_count=len(existing),
        )
        entities = [
            TradeExample(**{k: v for k, v in row.items() if k in TradeExample.model_fields})
            for row in existing
        ]
        return entities, _zero_usage()

    system_prompt = PROMPT_PASS2_TRADE_EXAMPLE_PATH.read_text(encoding="utf-8")
    output, usage, _history = call_structured(
        model=MODEL_PASS2,
        system=system_prompt,
        messages=[{"role": "user", "content": chunk["text"]}],
        schema=TradeExampleOutput,
    )

    save_trade_examples(
        db_path,
        source_chunk_id=chunk_id,
        prompt_version=PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
        output=output,
    )
    record_pass2_run(
        db_path,
        source_chunk_id=chunk_id,
        extractor="trade_example",
        prompt_version=PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
        entity_count=len(output.entities),
    )
    _log.info(
        "pass2.trade_example.extract.ok",
        chunk_id=chunk_id,
        prompt_version=PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
        entity_count=len(output.entities),
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_estimate_usd=usage.cost_estimate_usd,
    )
    return output.entities, usage
