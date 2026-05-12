"""Phase 2A v0.3 corrective slice — re-extract baseline TradeExample chunks
under the v2 prompt.

This is a one-off driver — once the v0.3 corrective slice ships, this module
is purely historical. It exists to populate v2 rows in the production
``trade_examples`` table alongside the existing v1 rows so the locked v2
prompt's behavior is reflected in the corpus.

Spec: docs/superpowers/specs/2026-05-11-pass2-te-corrective-reextract-design.md
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from trading_wiki.extractors.pass2 import trade_example as te_mod
from trading_wiki.extractors.pass2.trade_example import TradeExample

_log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ChunkRecord:
    """Per-chunk re-extraction summary."""

    chunk_id: int
    v1_count: int
    v2_count: int
    v2_entities: list[dict[str, Any]]
    cost_usd: float


@dataclass
class RunResult:
    """Aggregate of one corrective re-extract run."""

    run_id: str
    baseline_prompt_version: str
    target_prompt_version: str
    chunk_records: list[ChunkRecord]
    total_cost_usd: float = 0.0


def _discover_baseline_chunk_ids(
    db_path: Path,
    *,
    prompt_version: str,
) -> list[int]:
    """Return sorted unique chunk_ids with at least one TE row at the given
    ``prompt_version``.

    Used as the input set for the v2 re-extraction pass.
    """
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT source_chunk_id FROM trade_examples
            WHERE prompt_version = ?
            ORDER BY source_chunk_id
            """,
            (prompt_version,),
        ).fetchall()
    return [int(r[0]) for r in rows]


def _count_te_rows_at_version(db_path: Path, *, chunk_id: int, prompt_version: str) -> int:
    """Return the count of TE rows for ``(chunk_id, prompt_version)``."""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM trade_examples
            WHERE source_chunk_id = ? AND prompt_version = ?
            """,
            (chunk_id, prompt_version),
        ).fetchone()
    return int(row[0])


def _entity_summary(entity: TradeExample) -> dict[str, Any]:
    """Trim a TradeExample model down to audit-relevant fields for the run
    artifact. Avoids dumping the full 500-char description blobs."""
    return {
        "ticker": entity.ticker,
        "direction": entity.direction,
        "trade_date": entity.trade_date,
        "entry_price": entity.entry_price,
        "stop_price": entity.stop_price,
        "target_price": entity.target_price,
        "exit_price": entity.exit_price,
    }


def run_corrective_reextract(
    *,
    db_path: Path,
    baseline_prompt_version: str,
    target_prompt_path: Path,
    target_prompt_version: str,
) -> RunResult:
    """Drive the v2 re-extraction across all baseline TE chunks.

    Iterates chunks with at least one ``baseline_prompt_version`` TE row, calls
    ``extract_trade_examples_for_chunk`` per chunk under the v2 prompt
    (persisting v2 rows alongside v1 rows), and aggregates one ``ChunkRecord``
    per chunk into a ``RunResult``.
    """
    chunk_ids = _discover_baseline_chunk_ids(db_path, prompt_version=baseline_prompt_version)
    run_id = datetime.now().isoformat(timespec="seconds").replace(":", "-")
    records: list[ChunkRecord] = []
    total_cost = 0.0

    for chunk_id in chunk_ids:
        v1_count = _count_te_rows_at_version(
            db_path, chunk_id=chunk_id, prompt_version=baseline_prompt_version
        )
        entities, usage = te_mod.extract_trade_examples_for_chunk(
            chunk_id=chunk_id,
            db_path=db_path,
            prompt_path=target_prompt_path,
            prompt_version=target_prompt_version,
            persist=True,
        )
        records.append(
            ChunkRecord(
                chunk_id=chunk_id,
                v1_count=v1_count,
                v2_count=len(entities),
                v2_entities=[_entity_summary(e) for e in entities],
                cost_usd=usage.cost_estimate_usd,
            )
        )
        total_cost += usage.cost_estimate_usd
        _log.info(
            "corrective_reextract.chunk_done",
            chunk_id=chunk_id,
            v1_count=v1_count,
            v2_count=len(entities),
            cost_usd=usage.cost_estimate_usd,
        )

    return RunResult(
        run_id=run_id,
        baseline_prompt_version=baseline_prompt_version,
        target_prompt_version=target_prompt_version,
        chunk_records=records,
        total_cost_usd=total_cost,
    )
