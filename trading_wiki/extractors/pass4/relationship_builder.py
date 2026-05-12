"""Pass 4 — per-chunk relationship extraction.

For each Pass 1 chunk that has ≥2 Pass 2 entities written, build a manifest
of all entities from this chunk, prompt the LLM to enumerate triples that
trace back to the chunk text, and persist them to ``entity_relationships``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import structlog
from pydantic import Field

from trading_wiki.config import (
    MODEL_PASS4,
    PROMPT_PASS4_PATH,
    PROMPT_VERSION_PASS1,
    PROMPT_VERSION_PASS4,
)
from trading_wiki.core.db import load_chunk_by_id, load_chunks_for_version
from trading_wiki.core.llm import UsageRecord, call_structured
from trading_wiki.core.secrets import Settings
from trading_wiki.handlers.base import StrictModel

_log = structlog.get_logger(__name__)

EntityType = Literal["trade_example", "concept", "strategy", "setup", "rule", "market_condition"]
Predicate = Literal[
    "uses",
    "prerequisite_for",
    "variant_of",
    "contradicts",
    "supports",
    "depends_on",
    "illustrates",
    "applies_in",
]
Confidence = Literal["low", "medium", "high"]


class Relationship(StrictModel):
    subject_type: EntityType
    subject_id: int
    predicate: Predicate
    object_type: EntityType
    object_id: int
    confidence: Confidence
    rationale: str = Field(min_length=1, max_length=300)


class RelationshipOutput(StrictModel):
    entities: list[Relationship]


@dataclass
class Pass4Summary:
    chunks_seen: int = 0
    chunks_with_multiple_entities: int = 0
    chunks_processed: int = 0
    relationships_written: int = 0
    relationships_invalid_refs: int = 0
    failed_chunks: list[tuple[int, str]] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0


_ENTITY_TYPE_TABLES: dict[EntityType, tuple[str, str]] = {
    "trade_example": ("trade_examples", "ticker"),
    "concept": ("concepts", "term"),
    "strategy": ("strategies", "name"),
    "setup": ("setups", "name"),
    "rule": ("rules", "name"),
    "market_condition": ("market_conditions", "label"),
}


def _load_chunk_entities(db_path: Path, *, chunk_id: int) -> list[dict[str, Any]]:
    """Return all Pass 2 entities written from this chunk (across all types).

    Each item: ``{entity_type, entity_id, label}`` where ``label`` is the
    type's display field (``ticker`` for TE, ``term`` for Concept, ``name``
    for Strategy/Setup/Rule, ``label`` for MarketCondition).
    """
    out: list[dict[str, Any]] = []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        for etype, (table, display_col) in _ENTITY_TYPE_TABLES.items():
            for row in conn.execute(
                f"SELECT id, {display_col} AS display FROM {table} "
                "WHERE source_chunk_id = ? ORDER BY id",
                (chunk_id,),
            ):
                out.append(
                    {
                        "entity_type": etype,
                        "entity_id": int(row["id"]),
                        "label": str(row["display"]),
                    }
                )
    return out


def _render_entity_manifest(entities: list[dict[str, Any]]) -> str:
    """Render the entity list as a human-readable manifest for the LLM."""
    lines = ["## Entities extracted from this chunk:"]
    for e in entities:
        lines.append(f"  - type={e['entity_type']!s}  id={e['entity_id']!s}  label={e['label']!r}")
    return "\n".join(lines)


def _pass4_run_exists(db_path: Path, *, source_chunk_id: int, prompt_version: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM pass4_runs WHERE source_chunk_id = ? AND prompt_version = ?",
            (source_chunk_id, prompt_version),
        ).fetchone()
    return row is not None


def _record_pass4_run(
    db_path: Path,
    *,
    source_chunk_id: int,
    prompt_version: str,
    relationship_count: int,
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO pass4_runs
            (source_chunk_id, prompt_version, relationship_count, run_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                source_chunk_id,
                prompt_version,
                relationship_count,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()


def _persist_relationships(
    db_path: Path,
    *,
    chunk_id: int,
    relationships: list[Relationship],
    valid_ids: set[tuple[str, int]],
    prompt_version: str,
) -> tuple[int, int]:
    """Validate each relationship's subject/object refs against ``valid_ids``
    and persist the ones that pass. Returns ``(written_count, invalid_count)``.
    """
    now = datetime.now().isoformat(timespec="seconds")
    written = 0
    invalid = 0
    with sqlite3.connect(db_path) as conn:
        for r in relationships:
            sub_key = (r.subject_type, r.subject_id)
            obj_key = (r.object_type, r.object_id)
            if sub_key not in valid_ids or obj_key not in valid_ids or sub_key == obj_key:
                invalid += 1
                _log.warning(
                    "pass4.relationship.invalid_ref",
                    chunk_id=chunk_id,
                    subject=sub_key,
                    object=obj_key,
                )
                continue
            try:
                conn.execute(
                    """
                    INSERT INTO entity_relationships
                    (subject_type, subject_id, predicate, object_type, object_id,
                     source_chunk_id, confidence, rationale, prompt_version, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r.subject_type,
                        r.subject_id,
                        r.predicate,
                        r.object_type,
                        r.object_id,
                        chunk_id,
                        r.confidence,
                        r.rationale,
                        prompt_version,
                        now,
                    ),
                )
                written += 1
            except sqlite3.IntegrityError:
                # UNIQUE constraint — relationship already extracted at this
                # prompt_version. Treat as a no-op duplicate.
                pass
        conn.commit()
    return written, invalid


def extract_relationships_for_chunk(
    *,
    chunk_id: int,
    db_path: Path | None = None,
    prompt_path: Path | None = None,
    prompt_version: str | None = None,
    persist: bool = True,
) -> tuple[list[Relationship], UsageRecord, int, int]:
    """Extract relationships from one chunk's entities.

    Returns ``(relationships, usage, written_count, invalid_count)``. With
    ``persist=True`` and an existing ``pass4_runs`` row for this
    ``(chunk_id, prompt_version)``, returns previously-written rows reloaded
    from the DB with zero LLM cost.
    """
    db_path = Path(db_path) if db_path is not None else Settings().db_path
    prompt_path = Path(prompt_path) if prompt_path is not None else PROMPT_PASS4_PATH
    prompt_version = prompt_version or PROMPT_VERSION_PASS4

    chunk = load_chunk_by_id(db_path, chunk_id=chunk_id)
    if chunk is None:
        raise LookupError(f"unknown chunk_id={chunk_id}")

    entities = _load_chunk_entities(db_path, chunk_id=chunk_id)
    if len(entities) < 2:
        # No possible relationships if <2 entities.
        return [], _zero_usage(), 0, 0

    if persist and _pass4_run_exists(
        db_path, source_chunk_id=chunk_id, prompt_version=prompt_version
    ):
        _log.info(
            "pass4.relationship.idempotent_skip",
            chunk_id=chunk_id,
            prompt_version=prompt_version,
        )
        return [], _zero_usage(), 0, 0

    valid_ids = {(str(e["entity_type"]), int(e["entity_id"])) for e in entities}
    manifest = _render_entity_manifest(entities)
    system_prompt = prompt_path.read_text(encoding="utf-8")
    user_msg = (
        f"## Chunk text\n\n{chunk['text']}\n\n{manifest}\n\n"
        "Emit all relationship triples that trace back to the chunk text above."
    )

    output, usage, _history = call_structured(
        model=MODEL_PASS4,
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
        schema=RelationshipOutput,
    )

    written = 0
    invalid = 0
    if persist:
        written, invalid = _persist_relationships(
            db_path,
            chunk_id=chunk_id,
            relationships=output.entities,
            valid_ids=valid_ids,
            prompt_version=prompt_version,
        )
        _record_pass4_run(
            db_path,
            source_chunk_id=chunk_id,
            prompt_version=prompt_version,
            relationship_count=written,
        )

    _log.info(
        "pass4.relationship.extract.ok",
        chunk_id=chunk_id,
        prompt_version=prompt_version,
        persist=persist,
        proposed_count=len(output.entities),
        written_count=written,
        invalid_count=invalid,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_estimate_usd=usage.cost_estimate_usd,
    )
    return output.entities, usage, written, invalid


def _zero_usage() -> UsageRecord:
    return UsageRecord(
        model=MODEL_PASS4,
        input_tokens=0,
        output_tokens=0,
        cost_estimate_usd=0.0,
    )


def extract(*, content_id: int, db_path: Path | None = None) -> Pass4Summary:
    """Run Pass 4 over every Pass 1 chunk for ``content_id``."""
    db_path = Path(db_path) if db_path is not None else Settings().db_path
    chunks = load_chunks_for_version(
        db_path, content_id=content_id, prompt_version=PROMPT_VERSION_PASS1
    )
    if not chunks:
        raise RuntimeError(f"no Pass 1 chunks for content_id={content_id}")

    summary = Pass4Summary()
    for chunk in chunks:
        summary.chunks_seen += 1
        cid = chunk["id"]
        entities = _load_chunk_entities(db_path, chunk_id=cid)
        if len(entities) < 2:
            continue
        summary.chunks_with_multiple_entities += 1
        try:
            _proposed, usage, written, invalid = extract_relationships_for_chunk(
                chunk_id=cid, db_path=db_path
            )
            summary.chunks_processed += 1
            summary.relationships_written += written
            summary.relationships_invalid_refs += invalid
            summary.total_input_tokens += usage.input_tokens
            summary.total_output_tokens += usage.output_tokens
            summary.total_cost_usd += usage.cost_estimate_usd
        except Exception as e:
            summary.failed_chunks.append((cid, repr(e)))
            _log.warning("pass4.dispatch.failed", chunk_id=cid, error=repr(e))

    _log.info(
        "pass4.extract.ok",
        content_id=content_id,
        chunks_seen=summary.chunks_seen,
        chunks_with_multiple_entities=summary.chunks_with_multiple_entities,
        chunks_processed=summary.chunks_processed,
        relationships_written=summary.relationships_written,
        relationships_invalid_refs=summary.relationships_invalid_refs,
        total_cost_usd=summary.total_cost_usd,
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m trading_wiki.extractors.pass4.relationship_builder",
        description="Run Pass 4 (relationship extraction) on a single content_id.",
    )
    parser.add_argument("--content-id", type=int, required=True)
    args = parser.parse_args(argv)
    s = extract(content_id=args.content_id)
    print(
        f"Pass 4 for content_id={args.content_id}: "
        f"{s.chunks_with_multiple_entities} multi-entity chunks; "
        f"{s.relationships_written} relationships written; "
        f"{s.relationships_invalid_refs} invalid refs; "
        f"{len(s.failed_chunks)} failed chunks; "
        f"cost ≈ ${s.total_cost_usd:.4f}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
