"""Phase 2A v0.3 — contamination ablation harness for Pass 2 prompts.

Spec: docs/superpowers/specs/2026-05-10-pass2-contamination-ablation-design.md
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from trading_wiki.config import (
    PROMPT_PASS2_CONCEPT_BLIND_PATH,
    PROMPT_PASS2_TRADE_EXAMPLE_BLIND_PATH,
    PROMPT_VERSION_PASS1,
    PROMPT_VERSION_PASS2_CONCEPT,
    PROMPT_VERSION_PASS2_CONCEPT_BLIND,
    PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
    PROMPT_VERSION_PASS2_TRADE_EXAMPLE_BLIND,
)
from trading_wiki.core.db import (
    list_chunks_for_version_by_labels,
    load_concepts_for_version,
    load_trade_examples_for_version,
)
from trading_wiki.core.llm import UsageRecord
from trading_wiki.core.secrets import Settings
from trading_wiki.extractors.pass2.concept import extract_concepts_for_chunk
from trading_wiki.extractors.pass2.trade_example import extract_trade_examples_for_chunk

ROUTING_LABELS: tuple[str, ...] = (
    "strategy",
    "psychology",
    "market_commentary",
    "noise",
)

_OUTPUT_BASE_DIR = Path("data/ablation")

_BASELINE_DB_FIELDS: frozenset[str] = frozenset(
    {"id", "source_chunk_id", "prompt_version", "created_at"}
)


def _strip_db_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Return ``row`` minus DB-internal fields.

    Baseline rows loaded from the DB include columns the blind extractor's
    output doesn't have (the row's primary key, the source-chunk FK, the
    prompt_version it was extracted under, and its created_at timestamp).
    Comparing those fields against blind output always reports them as
    ``changed_fields``, which inflates the diff's noise floor. Strip them
    before passing baseline rows to ``build_priming_diff``.
    """
    return {k: v for k, v in row.items() if k not in _BASELINE_DB_FIELDS}


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


# ─── Routing audit builder ─────────────────────────────────────────────────

_EXCERPT_MAX_CHARS = 600


def build_routing_audit(
    *,
    non_example_chunks: list[dict[str, Any]],
    blind_results: dict[int, list[dict[str, Any]]],
) -> RoutingAudit:
    """Filter to chunks where blind TE returned >= 1 entity; format excerpts.

    The chunk text excerpt is truncated to ``_EXCERPT_MAX_CHARS`` characters
    with ``"..."`` appended when truncated. Entries are sorted by chunk_id
    ascending. ``total_chunks_audited`` reflects the size of
    ``non_example_chunks`` (the denominator) — not the number of entries
    returned.
    """
    entries: list[RoutingAuditEntry] = []
    for chunk in non_example_chunks:
        proposed = blind_results.get(chunk["id"], [])
        if not proposed:
            continue
        text: str = chunk["text"]
        excerpt = text if len(text) <= _EXCERPT_MAX_CHARS else text[:_EXCERPT_MAX_CHARS] + "..."
        entries.append(
            RoutingAuditEntry(
                chunk_id=chunk["id"],
                content_id=chunk["content_id"],
                chunk_label=chunk["label"],
                chunk_text_excerpt=excerpt,
                proposed_entities=proposed,
            )
        )

    entries.sort(key=lambda e: e.chunk_id)
    return RoutingAudit(entries=entries, total_chunks_audited=len(non_example_chunks))


# ─── Artifact writer ───────────────────────────────────────────────────────


def _render_priming_diff_md(
    *,
    extractor_name: str,
    diffs: list[PrimingDiff],
) -> str:
    if not diffs:
        return f"## {extractor_name}\n\nNo chunks sampled.\n"
    parts: list[str] = [f"## {extractor_name}\n"]
    for d in diffs:
        parts.append(
            f"### chunk_id={d.chunk_id} · content_id={d.content_id} · "
            f"label={d.chunk_label} · seq={d.chunk_seq}"
        )
        parts.append(
            f"- baseline_count: {d.baseline_count} · blind_count: {d.blind_count} · "
            f"verdict: **{d.overall_verdict}**\n"
        )
        for ed in d.entity_diffs:
            parts.append(f"- entity verdict: `{ed.verdict}`")
            if ed.changed_fields:
                parts.append(f"  - changed fields: {', '.join(ed.changed_fields)}")
            if ed.baseline is not None:
                parts.append(f"  - baseline: `{ed.baseline}`")
            if ed.blind is not None:
                parts.append(f"  - blind:    `{ed.blind}`")
        parts.append("")
    return "\n".join(parts)


def _render_routing_audit_md(audit: RoutingAudit) -> str:
    if not audit.entries:
        return f"# Routing audit\n\nNo routing misses found at n={audit.total_chunks_audited}.\n"
    parts: list[str] = [
        "# Routing audit\n",
        (
            f"{len(audit.entries)} of {audit.total_chunks_audited} non-example chunks "
            "produced TE entities under the blind prompt.\n"
        ),
    ]
    for e in audit.entries:
        parts.append(
            f"## chunk_id={e.chunk_id} · content_id={e.content_id} · label={e.chunk_label}"
        )
        parts.append(f"\n> {e.chunk_text_excerpt}\n")
        for ent in e.proposed_entities:
            parts.append(f"- proposed: `{ent}`")
        parts.append("")
    return "\n".join(parts)


def _render_summary_md(
    *,
    config: AblationConfig,
    te_priming_diffs: list[PrimingDiff],
    concept_priming_diffs: list[PrimingDiff],
    routing_audit: RoutingAudit,
) -> str:
    def _verdict_counts(diffs: list[PrimingDiff]) -> dict[str, int]:
        counts = {"identical": 0, "field_changed": 0, "count_changed": 0}
        for d in diffs:
            counts[d.overall_verdict] += 1
        return counts

    te_counts = _verdict_counts(te_priming_diffs)
    cn_counts = _verdict_counts(concept_priming_diffs)

    return (
        f"# Ablation summary\n\n"
        f"- run_id: `{config.run_id}`\n"
        f"- seed: {config.seed}\n"
        f"- total_cost_usd: {config.total_cost_usd:.4f}\n\n"
        f"## Priming arm — TE\n"
        f"- identical: {te_counts['identical']}\n"
        f"- field_changed: {te_counts['field_changed']}\n"
        f"- count_changed: {te_counts['count_changed']}\n\n"
        f"## Priming arm — Concept\n"
        f"- identical: {cn_counts['identical']}\n"
        f"- field_changed: {cn_counts['field_changed']}\n"
        f"- count_changed: {cn_counts['count_changed']}\n\n"
        f"## Routing arm\n"
        f"- {len(routing_audit.entries)} / {routing_audit.total_chunks_audited} "
        f"non-example chunks produced TE entities under the blind prompt\n\n"
        f"## Recommendation\n"
        f"_(fill in by hand after reviewing the diff and audit files)_\n"
    )


def write_run_artifacts(
    *,
    run_dir: Path,
    config: AblationConfig,
    te_priming_diffs: list[PrimingDiff],
    concept_priming_diffs: list[PrimingDiff],
    routing_audit: RoutingAudit,
) -> None:
    """Write config.json + priming_diff.md + routing_audit.md + summary.md."""
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "config.json").write_text(
        json.dumps(
            {
                "run_id": config.run_id,
                "seed": config.seed,
                "n_priming_te": config.n_priming_te,
                "n_priming_concept": config.n_priming_concept,
                "n_routing": config.n_routing,
                "sampled_chunk_ids": config.sampled_chunk_ids,
                "total_cost_usd": config.total_cost_usd,
                "total_input_tokens": config.total_input_tokens,
                "total_output_tokens": config.total_output_tokens,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    priming_md = (
        "# Priming diff\n\n"
        + _render_priming_diff_md(extractor_name="trade_example", diffs=te_priming_diffs)
        + "\n"
        + _render_priming_diff_md(extractor_name="concept", diffs=concept_priming_diffs)
    )
    (run_dir / "priming_diff.md").write_text(priming_md, encoding="utf-8")
    (run_dir / "routing_audit.md").write_text(
        _render_routing_audit_md(routing_audit), encoding="utf-8"
    )
    (run_dir / "summary.md").write_text(
        _render_summary_md(
            config=config,
            te_priming_diffs=te_priming_diffs,
            concept_priming_diffs=concept_priming_diffs,
            routing_audit=routing_audit,
        ),
        encoding="utf-8",
    )


# ─── CLI ───────────────────────────────────────────────────────────────────


def _entities_to_dicts(entities: list[Any]) -> list[dict[str, Any]]:
    return [e.model_dump() if hasattr(e, "model_dump") else dict(e) for e in entities]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m trading_wiki.extractors.pass2.ablation",
        description="Run the Pass 2 contamination-ablation harness.",
    )
    parser.add_argument("--n-priming-te", type=int, default=10)
    parser.add_argument("--n-priming-concept", type=int, default=10)
    parser.add_argument("--n-routing", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    db_path = Settings().db_path
    samples = sample_chunks_for_ablation(
        db_path=db_path,
        n_priming_te=args.n_priming_te,
        n_priming_concept=args.n_priming_concept,
        n_routing=args.n_routing,
        seed=args.seed,
    )

    total_in = 0
    total_out = 0
    total_cost = 0.0

    def _accumulate(usage: UsageRecord) -> None:
        nonlocal total_in, total_out, total_cost
        total_in += usage.input_tokens
        total_out += usage.output_tokens
        total_cost += usage.cost_estimate_usd

    # TE priming arm
    te_diffs: list[PrimingDiff] = []
    for chunk in samples.te_priming:
        baseline_rows = load_trade_examples_for_version(
            db_path,
            source_chunk_id=chunk["id"],
            prompt_version=PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
        )
        blind_entities, usage = extract_trade_examples_for_chunk(
            chunk_id=chunk["id"],
            db_path=db_path,
            prompt_path=PROMPT_PASS2_TRADE_EXAMPLE_BLIND_PATH,
            prompt_version=PROMPT_VERSION_PASS2_TRADE_EXAMPLE_BLIND,
            persist=False,
        )
        _accumulate(usage)
        te_diffs.append(
            build_priming_diff(
                chunk=chunk,
                baseline=[_strip_db_fields(r) for r in baseline_rows],
                blind=_entities_to_dicts(blind_entities),
                match_key="ticker",
            )
        )

    # Concept priming arm
    concept_diffs: list[PrimingDiff] = []
    for chunk in samples.concept_priming:
        baseline_rows = load_concepts_for_version(
            db_path,
            source_chunk_id=chunk["id"],
            prompt_version=PROMPT_VERSION_PASS2_CONCEPT,
        )
        blind_concepts, usage = extract_concepts_for_chunk(
            chunk_id=chunk["id"],
            db_path=db_path,
            prompt_path=PROMPT_PASS2_CONCEPT_BLIND_PATH,
            prompt_version=PROMPT_VERSION_PASS2_CONCEPT_BLIND,
            persist=False,
        )
        _accumulate(usage)
        concept_diffs.append(
            build_priming_diff(
                chunk=chunk,
                baseline=[_strip_db_fields(r) for r in baseline_rows],
                blind=_entities_to_dicts(blind_concepts),
                match_key="term",
            )
        )

    # Routing arm — run blind TE extractor over non-example chunks
    routing_blind_results: dict[int, list[dict[str, Any]]] = {}
    for chunk in samples.routing:
        blind_entities, usage = extract_trade_examples_for_chunk(
            chunk_id=chunk["id"],
            db_path=db_path,
            prompt_path=PROMPT_PASS2_TRADE_EXAMPLE_BLIND_PATH,
            prompt_version=PROMPT_VERSION_PASS2_TRADE_EXAMPLE_BLIND,
            persist=False,
        )
        _accumulate(usage)
        routing_blind_results[chunk["id"]] = _entities_to_dicts(blind_entities)

    routing_audit = build_routing_audit(
        non_example_chunks=samples.routing,
        blind_results=routing_blind_results,
    )

    run_id = datetime.now().isoformat(timespec="seconds").replace(":", "-")
    config = AblationConfig(
        run_id=run_id,
        seed=args.seed,
        n_priming_te=args.n_priming_te,
        n_priming_concept=args.n_priming_concept,
        n_routing=args.n_routing,
        sampled_chunk_ids={
            "te_priming": [c["id"] for c in samples.te_priming],
            "concept_priming": [c["id"] for c in samples.concept_priming],
            "routing": [c["id"] for c in samples.routing],
        },
        total_cost_usd=total_cost,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
    )

    run_dir = _OUTPUT_BASE_DIR / run_id
    write_run_artifacts(
        run_dir=run_dir,
        config=config,
        te_priming_diffs=te_diffs,
        concept_priming_diffs=concept_diffs,
        routing_audit=routing_audit,
    )

    print(f"Wrote ablation artifacts to {run_dir}")
    print(
        f"TE priming: {len(te_diffs)} diffs · "
        f"Concept priming: {len(concept_diffs)} diffs · "
        f"Routing: {len(routing_audit.entries)}/{routing_audit.total_chunks_audited} "
        f"misses · cost ~${total_cost:.4f}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
