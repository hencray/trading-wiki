"""Phase 2A Slice 6 — Pass 2 Strategy extractor (per-chunk candidates).

Cross-chunk merging into canonical Strategy entities is deferred to a Pass 3
slice that generalizes the Concept resolver pattern. Each row written here
is a *candidate* Strategy drawn from one chunk's language.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import structlog
from pydantic import Field

from trading_wiki.config import (
    MODEL_PASS2,
    PROMPT_PASS2_STRATEGY_PATH,
    PROMPT_VERSION_PASS2_STRATEGY,
)
from trading_wiki.core.db import (
    load_chunk_by_id,
    load_strategies_for_version,
    pass2_run_exists,
    record_pass2_run,
    save_strategies,
)
from trading_wiki.core.llm import UsageRecord, call_structured
from trading_wiki.core.secrets import Settings
from trading_wiki.handlers.base import StrictModel

_log = structlog.get_logger(__name__)

Confidence = Literal["low", "medium", "high"]


class Strategy(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    thesis: str = Field(min_length=10, max_length=400)
    entry_rules: str = Field(min_length=1, max_length=800)
    exit_rules: str = Field(min_length=1, max_length=800)
    risk_management: str | None = Field(default=None, max_length=400)
    indicators_used: list[str] = Field(default_factory=list, max_length=10)
    timeframe: str | None = Field(default=None, max_length=50)
    instruments: list[str] = Field(default_factory=list, max_length=10)
    codeability_score: int | None = Field(default=None, ge=1, le=5)
    confidence: Confidence


class StrategyOutput(StrictModel):
    entities: list[Strategy]


def _zero_usage() -> UsageRecord:
    return UsageRecord(
        model=MODEL_PASS2,
        input_tokens=0,
        output_tokens=0,
        cost_estimate_usd=0.0,
    )


def extract_strategies_for_chunk(
    *,
    chunk_id: int,
    db_path: Path | None = None,
    prompt_path: Path | None = None,
    prompt_version: str | None = None,
    persist: bool = True,
) -> tuple[list[Strategy], UsageRecord]:
    """Run the Strategy extractor against one chunk_id.

    Returns ``(entities, usage)``. Mirrors the v0.2 per-chunk pattern from
    ``concept.py`` / ``trade_example.py``. Idempotent against
    ``(chunk_id, prompt_version)`` via the ``pass2_runs`` table.
    """
    db_path = Path(db_path) if db_path is not None else Settings().db_path
    prompt_path = Path(prompt_path) if prompt_path is not None else PROMPT_PASS2_STRATEGY_PATH
    prompt_version = prompt_version or PROMPT_VERSION_PASS2_STRATEGY

    chunk = load_chunk_by_id(db_path, chunk_id=chunk_id)
    if chunk is None:
        raise LookupError(f"unknown chunk_id={chunk_id}")

    if persist and pass2_run_exists(
        db_path,
        source_chunk_id=chunk_id,
        extractor="strategy",
        prompt_version=prompt_version,
    ):
        existing = load_strategies_for_version(
            db_path,
            source_chunk_id=chunk_id,
            prompt_version=prompt_version,
        )
        _log.info(
            "pass2.strategy.idempotent_skip",
            chunk_id=chunk_id,
            prompt_version=prompt_version,
            existing_count=len(existing),
        )
        entities = [
            Strategy(**{k: v for k, v in row.items() if k in Strategy.model_fields})
            for row in existing
        ]
        return entities, _zero_usage()

    system_prompt = prompt_path.read_text(encoding="utf-8")
    output, usage, _history = call_structured(
        model=MODEL_PASS2,
        system=system_prompt,
        messages=[{"role": "user", "content": chunk["text"]}],
        schema=StrategyOutput,
    )

    if persist:
        save_strategies(
            db_path,
            source_chunk_id=chunk_id,
            prompt_version=prompt_version,
            output=output,
        )
        record_pass2_run(
            db_path,
            source_chunk_id=chunk_id,
            extractor="strategy",
            prompt_version=prompt_version,
            entity_count=len(output.entities),
        )

    _log.info(
        "pass2.strategy.extract.ok",
        chunk_id=chunk_id,
        prompt_version=prompt_version,
        persist=persist,
        entity_count=len(output.entities),
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_estimate_usd=usage.cost_estimate_usd,
    )
    return output.entities, usage
