"""Sample picker for the review UI. Composes DB rows into ReviewItem records."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from trading_wiki.core.db import (
    list_concepts_for_content,
    list_trade_examples_for_content,
    load_chunk_by_id,
)
from trading_wiki.review.findings import EntityType

SampleMode = Literal["stratified", "all", "random"]


@dataclass(frozen=True)
class ReviewItem:
    entity_type: EntityType
    entity_id: int
    chunk_id: int
    chunk_label: str
    chunk_text: str
    entity_data: dict[str, Any]
    prompt_version: str


def _all_items_for_content(
    db_path: Path | str,
    *,
    content_id: int,
    entity_types: list[EntityType],
) -> list[ReviewItem]:
    items: list[ReviewItem] = []
    chunk_cache: dict[int, dict[str, Any]] = {}

    def _chunk(chunk_id: int) -> dict[str, Any]:
        if chunk_id not in chunk_cache:
            row = load_chunk_by_id(db_path, chunk_id=chunk_id)
            if row is None:
                raise ValueError(f"chunk {chunk_id} not found")
            chunk_cache[chunk_id] = row
        return chunk_cache[chunk_id]

    if "trade_example" in entity_types:
        for row in list_trade_examples_for_content(db_path, content_id=content_id):
            ch = _chunk(row["source_chunk_id"])
            items.append(
                ReviewItem(
                    entity_type="trade_example",
                    entity_id=row["id"],
                    chunk_id=ch["id"],
                    chunk_label=ch["label"],
                    chunk_text=ch["text"],
                    entity_data=row,
                    prompt_version=row["prompt_version"],
                )
            )
    if "concept" in entity_types:
        for row in list_concepts_for_content(db_path, content_id=content_id):
            ch = _chunk(row["source_chunk_id"])
            items.append(
                ReviewItem(
                    entity_type="concept",
                    entity_id=row["id"],
                    chunk_id=ch["id"],
                    chunk_label=ch["label"],
                    chunk_text=ch["text"],
                    entity_data=row,
                    prompt_version=row["prompt_version"],
                )
            )
    return items


def sample_items(
    db_path: Path | str,
    *,
    content_id: int,
    entity_types: list[EntityType],
    mode: SampleMode,
    n: int = 0,
    exclude_ids: set[tuple[EntityType, int]] | None = None,
    rng_seed: int | None = None,
) -> list[ReviewItem]:
    """Return a sample of items for review.

    ``mode="all"`` returns every item subject to ``exclude_ids`` and
    ``entity_types``. Other modes are added in later tasks.
    """
    excluded = exclude_ids or set()
    pool = [
        i
        for i in _all_items_for_content(db_path, content_id=content_id, entity_types=entity_types)
        if (i.entity_type, i.entity_id) not in excluded
    ]
    if mode == "all":
        return pool
    if mode == "random":
        rng = random.Random(rng_seed)
        if n >= len(pool):
            return pool
        return rng.sample(pool, n)
    if mode == "stratified":
        rng = random.Random(rng_seed)
        buckets: dict[str, list[ReviewItem]] = {}
        for item in pool:
            buckets.setdefault(item.chunk_label, []).append(item)
        if not buckets:
            return []
        labels = list(buckets)
        base, remainder = divmod(n, len(labels))
        order = sorted(labels, key=lambda lbl: (-len(buckets[lbl]), labels.index(lbl)))
        targets: dict[str, int] = dict.fromkeys(labels, base)
        for lbl in order[:remainder]:
            targets[lbl] += 1
        out: list[ReviewItem] = []
        for lbl in labels:
            bucket = buckets[lbl]
            take = min(targets[lbl], len(bucket))
            out.extend(rng.sample(bucket, take) if take < len(bucket) else bucket)
        return out
    raise NotImplementedError(f"mode={mode} not yet implemented")
