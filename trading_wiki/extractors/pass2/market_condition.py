"""Phase 2A Slice 6c — Pass 2 MarketCondition extractor."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import structlog
from pydantic import Field

from trading_wiki.config import (
    MODEL_PASS2,
    PROMPT_PASS2_MARKET_CONDITION_PATH,
    PROMPT_VERSION_PASS2_MARKET_CONDITION,
)
from trading_wiki.core.db import (
    load_chunk_by_id,
    load_market_conditions_for_version,
    pass2_run_exists,
    record_pass2_run,
    save_market_conditions,
)
from trading_wiki.core.llm import UsageRecord, call_structured
from trading_wiki.core.secrets import Settings
from trading_wiki.handlers.base import StrictModel

_log = structlog.get_logger(__name__)

Confidence = Literal["low", "medium", "high"]


class MarketCondition(StrictModel):
    label: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=10, max_length=400)
    time_window: str | None = Field(default=None, max_length=100)
    affected_instruments: list[str] = Field(default_factory=list, max_length=20)
    confidence: Confidence


class MarketConditionOutput(StrictModel):
    entities: list[MarketCondition]


def _zero_usage() -> UsageRecord:
    return UsageRecord(
        model=MODEL_PASS2,
        input_tokens=0,
        output_tokens=0,
        cost_estimate_usd=0.0,
    )


def extract_market_conditions_for_chunk(
    *,
    chunk_id: int,
    db_path: Path | None = None,
    prompt_path: Path | None = None,
    prompt_version: str | None = None,
    persist: bool = True,
) -> tuple[list[MarketCondition], UsageRecord]:
    """Run the MarketCondition extractor against one chunk_id."""
    db_path = Path(db_path) if db_path is not None else Settings().db_path
    prompt_path = (
        Path(prompt_path) if prompt_path is not None else PROMPT_PASS2_MARKET_CONDITION_PATH
    )
    prompt_version = prompt_version or PROMPT_VERSION_PASS2_MARKET_CONDITION

    chunk = load_chunk_by_id(db_path, chunk_id=chunk_id)
    if chunk is None:
        raise LookupError(f"unknown chunk_id={chunk_id}")

    if persist and pass2_run_exists(
        db_path,
        source_chunk_id=chunk_id,
        extractor="market_condition",
        prompt_version=prompt_version,
    ):
        existing = load_market_conditions_for_version(
            db_path,
            source_chunk_id=chunk_id,
            prompt_version=prompt_version,
        )
        _log.info(
            "pass2.market_condition.idempotent_skip",
            chunk_id=chunk_id,
            prompt_version=prompt_version,
            existing_count=len(existing),
        )
        entities = [
            MarketCondition(**{k: v for k, v in row.items() if k in MarketCondition.model_fields})
            for row in existing
        ]
        return entities, _zero_usage()

    system_prompt = prompt_path.read_text(encoding="utf-8")
    output, usage, _history = call_structured(
        model=MODEL_PASS2,
        system=system_prompt,
        messages=[{"role": "user", "content": chunk["text"]}],
        schema=MarketConditionOutput,
    )

    if persist:
        save_market_conditions(
            db_path,
            source_chunk_id=chunk_id,
            prompt_version=prompt_version,
            output=output,
        )
        record_pass2_run(
            db_path,
            source_chunk_id=chunk_id,
            extractor="market_condition",
            prompt_version=prompt_version,
            entity_count=len(output.entities),
        )

    _log.info(
        "pass2.market_condition.extract.ok",
        chunk_id=chunk_id,
        prompt_version=prompt_version,
        persist=persist,
        entity_count=len(output.entities),
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_estimate_usd=usage.cost_estimate_usd,
    )
    return output.entities, usage
