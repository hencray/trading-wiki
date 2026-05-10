"""Phase 2A v0.3 — contamination ablation harness for Pass 2 prompts.

Spec: docs/superpowers/specs/2026-05-10-pass2-contamination-ablation-design.md
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from trading_wiki.config import PROMPT_VERSION_PASS1
from trading_wiki.core.db import list_chunks_for_version_by_labels

ROUTING_LABELS: tuple[str, ...] = (
    "strategy",
    "psychology",
    "market_commentary",
    "noise",
)


# ─── Shared types (used across Tasks 6-11) ─────────────────────────────────

EntityVerdict = Literal["identical", "field_changed", "added", "removed"]
OverallVerdict = Literal["identical", "count_changed", "field_changed"]


@dataclass(frozen=True)
class AblationSamples:
    te_priming: list[dict[str, Any]]
    concept_priming: list[dict[str, Any]]
    routing: list[dict[str, Any]]


@dataclass(frozen=True)
class EntityDiff:
    verdict: EntityVerdict
    baseline: dict[str, Any] | None
    blind: dict[str, Any] | None
    changed_fields: list[str]


@dataclass(frozen=True)
class PrimingDiff:
    chunk_id: int
    content_id: int
    chunk_label: str
    chunk_seq: int
    baseline_count: int
    blind_count: int
    overall_verdict: OverallVerdict
    entity_diffs: list[EntityDiff]


@dataclass(frozen=True)
class RoutingAuditEntry:
    chunk_id: int
    content_id: int
    chunk_label: str
    chunk_text_excerpt: str
    proposed_entities: list[dict[str, Any]]


@dataclass(frozen=True)
class RoutingAudit:
    entries: list[RoutingAuditEntry]
    total_chunks_audited: int


@dataclass(frozen=True)
class AblationConfig:
    run_id: str
    seed: int
    n_priming_te: int
    n_priming_concept: int
    n_routing: int
    sampled_chunk_ids: dict[str, list[int]]
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int


# ─── Sampler ───────────────────────────────────────────────────────────────


def _sample_at_most(rows: list[dict[str, Any]], n: int, rng: random.Random) -> list[dict[str, Any]]:
    if n >= len(rows):
        return list(rows)
    return rng.sample(rows, n)


def sample_chunks_for_ablation(
    *,
    db_path: Path | str,
    n_priming_te: int,
    n_priming_concept: int,
    n_routing: int,
    seed: int,
) -> AblationSamples:
    """Pull three deterministic stratified samples from the v1 chunks table.

    All three strata are read at ``PROMPT_VERSION_PASS1`` (the locked v1
    classifier output). Each stratum gets its own ``random.Random`` seeded
    deterministically so per-stratum sample sizes can change without
    perturbing the others.
    """
    te_pool = list_chunks_for_version_by_labels(
        db_path, labels=["example"], prompt_version=PROMPT_VERSION_PASS1
    )
    concept_pool = list_chunks_for_version_by_labels(
        db_path, labels=["concept", "qa"], prompt_version=PROMPT_VERSION_PASS1
    )
    routing_pool = list_chunks_for_version_by_labels(
        db_path, labels=list(ROUTING_LABELS), prompt_version=PROMPT_VERSION_PASS1
    )

    return AblationSamples(
        te_priming=_sample_at_most(te_pool, n_priming_te, random.Random(seed)),
        concept_priming=_sample_at_most(concept_pool, n_priming_concept, random.Random(seed + 1)),
        routing=_sample_at_most(routing_pool, n_routing, random.Random(seed + 2)),
    )


# ─── Priming diff builder ──────────────────────────────────────────────────


def _diff_fields(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    keys = set(a) | set(b)
    return sorted(k for k in keys if a.get(k) != b.get(k))


def build_priming_diff(
    *,
    chunk: dict[str, Any],
    baseline: list[dict[str, Any]],
    blind: list[dict[str, Any]],
    match_key: str,
) -> PrimingDiff:
    """Pair-and-diff baseline vs blind entities for one chunk.

    Pairs entities by ``match_key`` (string-equal). Unpaired baseline rows are
    ``removed``; unpaired blind rows are ``added``; paired rows with any
    differing field are ``field_changed``; paired rows with no difference are
    ``identical``.
    """
    baseline_by_key = {row[match_key]: row for row in baseline}
    blind_by_key = {row[match_key]: row for row in blind}

    diffs: list[EntityDiff] = []
    for key in baseline_by_key.keys() | blind_by_key.keys():
        b_row = baseline_by_key.get(key)
        n_row = blind_by_key.get(key)
        if b_row is not None and n_row is None:
            diffs.append(
                EntityDiff(verdict="removed", baseline=b_row, blind=None, changed_fields=[])
            )
        elif b_row is None and n_row is not None:
            diffs.append(EntityDiff(verdict="added", baseline=None, blind=n_row, changed_fields=[]))
        else:
            assert b_row is not None
            assert n_row is not None
            changed = _diff_fields(b_row, n_row)
            diffs.append(
                EntityDiff(
                    verdict="field_changed" if changed else "identical",
                    baseline=b_row,
                    blind=n_row,
                    changed_fields=changed,
                )
            )

    if len(baseline) != len(blind):
        overall: OverallVerdict = "count_changed"
    elif any(d.verdict == "field_changed" for d in diffs):
        overall = "field_changed"
    else:
        overall = "identical"

    return PrimingDiff(
        chunk_id=chunk["id"],
        content_id=chunk["content_id"],
        chunk_label=chunk["label"],
        chunk_seq=chunk["seq"],
        baseline_count=len(baseline),
        blind_count=len(blind),
        overall_verdict=overall,
        entity_diffs=diffs,
    )
