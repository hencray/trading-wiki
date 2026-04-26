"""Phase 2A v0.2 — Pass 2 dispatcher.

Routes Pass 1 chunks to per-type entity extractors based on chunk label.
See docs/superpowers/specs/2026-04-25-phase-2a-pass2-design.md §5.5.
"""

from dataclasses import dataclass, field
from pathlib import Path

import structlog

from trading_wiki.config import (
    PASS2_LABEL_ROUTES,
    PROMPT_VERSION_PASS1,
)
from trading_wiki.core.db import load_chunks_for_version
from trading_wiki.core.llm import UsageRecord
from trading_wiki.core.secrets import Settings
from trading_wiki.extractors.pass2.concept import extract_concepts_for_chunk
from trading_wiki.extractors.pass2.trade_example import (
    extract_trade_examples_for_chunk,
)

_log = structlog.get_logger(__name__)


@dataclass
class Pass2Summary:
    chunks_seen: int = 0
    chunks_routed: int = 0
    trade_examples_written: int = 0
    concepts_written: int = 0
    failed_chunks: list[tuple[int, str]] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0


def _accumulate(summary: Pass2Summary, usage: UsageRecord) -> None:
    summary.total_input_tokens += usage.input_tokens
    summary.total_output_tokens += usage.output_tokens
    summary.total_cost_usd += usage.cost_estimate_usd


def extract(*, content_id: int, db_path: Path | None = None) -> Pass2Summary:
    """Run Pass 2 over every Pass 1 chunk for ``content_id``.

    Spec §5.5 data flow. Per-chunk failures are caught and recorded so one
    bad chunk doesn't lose work on the rest; idempotency in the per-type
    extractors makes re-running this function free for already-succeeded chunks.

    Raises:
        RuntimeError: no Pass 1 chunks exist for this ``content_id``.
    """
    db_path = Path(db_path) if db_path is not None else Settings().db_path

    chunks = load_chunks_for_version(
        db_path,
        content_id=content_id,
        prompt_version=PROMPT_VERSION_PASS1,
    )
    if not chunks:
        raise RuntimeError(f"no Pass 1 chunks for content_id={content_id}; run Pass 1 first.")

    summary = Pass2Summary()
    te_labels = PASS2_LABEL_ROUTES["trade_example"]
    co_labels = PASS2_LABEL_ROUTES["concept"]

    for chunk in chunks:
        summary.chunks_seen += 1
        label = chunk["label"]
        chunk_id = chunk["id"]

        if label in te_labels:
            summary.chunks_routed += 1
            try:
                te_entities, te_usage = extract_trade_examples_for_chunk(
                    chunk_id=chunk_id,
                    db_path=db_path,
                )
                summary.trade_examples_written += len(te_entities)
                _accumulate(summary, te_usage)
            except Exception as e:
                # Per-chunk resilience by design: one bad chunk shouldn't lose work on others.
                summary.failed_chunks.append((chunk_id, repr(e)))
                _log.warning(
                    "pass2.dispatch.failed",
                    chunk_id=chunk_id,
                    label=label,
                    error=repr(e),
                )
        elif label in co_labels:
            summary.chunks_routed += 1
            try:
                co_entities, co_usage = extract_concepts_for_chunk(
                    chunk_id=chunk_id,
                    db_path=db_path,
                )
                summary.concepts_written += len(co_entities)
                _accumulate(summary, co_usage)
            except Exception as e:
                # Per-chunk resilience by design: one bad chunk shouldn't lose work on others.
                summary.failed_chunks.append((chunk_id, repr(e)))
                _log.warning(
                    "pass2.dispatch.failed",
                    chunk_id=chunk_id,
                    label=label,
                    error=repr(e),
                )
        # else: not routed in v0.2; fall through.

    _log.info(
        "pass2.extract.ok",
        content_id=content_id,
        chunks_seen=summary.chunks_seen,
        chunks_routed=summary.chunks_routed,
        trade_examples_written=summary.trade_examples_written,
        concepts_written=summary.concepts_written,
        failed_count=len(summary.failed_chunks),
        total_input_tokens=summary.total_input_tokens,
        total_output_tokens=summary.total_output_tokens,
        total_cost_usd=summary.total_cost_usd,
    )
    return summary
