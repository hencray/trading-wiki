"""Phase 2A v0.2 — Pass 2 Concept extractor."""

from pathlib import Path
from typing import Literal

import structlog
from pydantic import Field

from trading_wiki.config import (
    MODEL_PASS2,
    PROMPT_PASS2_CONCEPT_PATH,
    PROMPT_VERSION_PASS2_CONCEPT,
)
from trading_wiki.core.db import (
    load_chunk_by_id,
    load_concepts_for_version,
    pass2_run_exists,
    record_pass2_run,
    save_concepts,
)
from trading_wiki.core.llm import UsageRecord, call_structured
from trading_wiki.core.secrets import Settings
from trading_wiki.handlers.base import StrictModel

_log = structlog.get_logger(__name__)

Confidence = Literal["low", "medium", "high"]


class Concept(StrictModel):
    term: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=10, max_length=400)
    related_terms: list[str] = Field(default_factory=list, max_length=15)
    confidence: Confidence


class ConceptOutput(StrictModel):
    entities: list[Concept]


def _zero_usage() -> UsageRecord:
    return UsageRecord(
        model=MODEL_PASS2,
        input_tokens=0,
        output_tokens=0,
        cost_estimate_usd=0.0,
    )


def extract_concepts_for_chunk(
    *,
    chunk_id: int,
    db_path: Path | None = None,
) -> tuple[list[Concept], UsageRecord]:
    """Run the Concept extractor against one chunk_id.

    Returns ``(entities, usage)``. On idempotency hit, ``entities`` is rebuilt
    from the stored rows (with ``related_terms`` JSON-decoded back to a list)
    and ``usage`` is a zero-cost record.

    Spec §5.4 data flow.
    """
    db_path = Path(db_path) if db_path is not None else Settings().db_path

    chunk = load_chunk_by_id(db_path, chunk_id=chunk_id)
    if chunk is None:
        raise LookupError(f"unknown chunk_id={chunk_id}")

    if pass2_run_exists(
        db_path,
        source_chunk_id=chunk_id,
        extractor="concept",
        prompt_version=PROMPT_VERSION_PASS2_CONCEPT,
    ):
        existing = load_concepts_for_version(
            db_path,
            source_chunk_id=chunk_id,
            prompt_version=PROMPT_VERSION_PASS2_CONCEPT,
        )
        _log.info(
            "pass2.concept.idempotent_skip",
            chunk_id=chunk_id,
            prompt_version=PROMPT_VERSION_PASS2_CONCEPT,
            existing_count=len(existing),
        )
        entities = [
            Concept(**{k: v for k, v in row.items() if k in Concept.model_fields})
            for row in existing
        ]
        return entities, _zero_usage()

    system_prompt = PROMPT_PASS2_CONCEPT_PATH.read_text(encoding="utf-8")
    output, usage, _history = call_structured(
        model=MODEL_PASS2,
        system=system_prompt,
        messages=[{"role": "user", "content": chunk["text"]}],
        schema=ConceptOutput,
    )

    save_concepts(
        db_path,
        source_chunk_id=chunk_id,
        prompt_version=PROMPT_VERSION_PASS2_CONCEPT,
        output=output,
    )
    record_pass2_run(
        db_path,
        source_chunk_id=chunk_id,
        extractor="concept",
        prompt_version=PROMPT_VERSION_PASS2_CONCEPT,
        entity_count=len(output.entities),
    )
    _log.info(
        "pass2.concept.extract.ok",
        chunk_id=chunk_id,
        prompt_version=PROMPT_VERSION_PASS2_CONCEPT,
        entity_count=len(output.entities),
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_estimate_usd=usage.cost_estimate_usd,
    )
    return output.entities, usage
