"""Phase 2A v0.3 corrective slice — re-extract baseline TradeExample chunks
under the v2 prompt.

This is a one-off driver — once the v0.3 corrective slice ships, this module
is purely historical. It exists to populate v2 rows in the production
``trade_examples`` table alongside the existing v1 rows so the locked v2
prompt's behavior is reflected in the corpus.

Spec: docs/superpowers/specs/2026-05-11-pass2-te-corrective-reextract-design.md
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from trading_wiki.config import (
    PROMPT_PASS2_TRADE_EXAMPLE_V2_PATH,
    PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
    PROMPT_VERSION_PASS2_TRADE_EXAMPLE_V2,
)
from trading_wiki.core.secrets import Settings
from trading_wiki.extractors.pass2 import trade_example as te_mod
from trading_wiki.extractors.pass2.trade_example import TradeExample

_log = structlog.get_logger(__name__)

_OUTPUT_BASE_DIR = Path("data/corrective")


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


def _render_summary_md(result: RunResult) -> str:
    """Render a per-chunk markdown summary of one RunResult."""
    lines = [
        "# Corrective Re-extract Summary",
        "",
        f"- run_id: `{result.run_id}`",
        f"- baseline: `{result.baseline_prompt_version}`",
        f"- target: `{result.target_prompt_version}`",
        f"- Chunks processed: {len(result.chunk_records)}",
        f"- Total cost: ${result.total_cost_usd:.2f}",
        "",
        "## Per-chunk changes",
        "",
    ]
    for r in result.chunk_records:
        lines.append(
            f"- chunk_id={r.chunk_id}: v1={r.v1_count} → v2={r.v2_count} (${r.cost_usd:.4f})"
        )
        for e in r.v2_entities:
            price_fields = [
                f"{k}={v}" for k, v in e.items() if k.endswith("_price") and v is not None
            ]
            if price_fields:
                lines.append(
                    f"  - {e.get('ticker')} {e.get('direction')}: " + ", ".join(price_fields)
                )
            else:
                lines.append(f"  - {e.get('ticker')} {e.get('direction')}: (no prices)")
        lines.append("")
    return "\n".join(lines)


def write_corrective_artifacts(
    *,
    result: RunResult,
    output_base_dir: Path | None = None,
) -> Path:
    """Write ``summary.json`` and ``summary.md`` to ``<base>/<run_id>/``.

    Returns the run directory path.
    """
    base = output_base_dir if output_base_dir is not None else _OUTPUT_BASE_DIR
    run_dir = base / result.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "run_id": result.run_id,
        "baseline_prompt_version": result.baseline_prompt_version,
        "target_prompt_version": result.target_prompt_version,
        "total_cost_usd": result.total_cost_usd,
        "chunk_records": [
            {
                "chunk_id": r.chunk_id,
                "v1_count": r.v1_count,
                "v2_count": r.v2_count,
                "v2_entities": r.v2_entities,
                "cost_usd": r.cost_usd,
            }
            for r in result.chunk_records
        ],
    }
    (run_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (run_dir / "summary.md").write_text(_render_summary_md(result), encoding="utf-8")
    return run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m trading_wiki.extractors.pass2.corrective_reextract",
        description=(
            "Re-extract Pass 2 TradeExample chunks under the v2 prompt. "
            "One-off driver for the Phase 2A v0.3 corrective slice."
        ),
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Override the production DB path. Defaults to Settings().db_path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=("List baseline chunk_ids and exit without re-extracting or writing any artifacts."),
    )
    args = parser.parse_args(argv)

    db_path = args.db_path if args.db_path is not None else Settings().db_path
    chunk_ids = _discover_baseline_chunk_ids(
        db_path,
        prompt_version=PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
    )

    if args.dry_run:
        print(
            f"Would re-extract {len(chunk_ids)} chunks under "
            f"{PROMPT_VERSION_PASS2_TRADE_EXAMPLE_V2}:"
        )
        for chunk_id in chunk_ids:
            print(f"  chunk_id={chunk_id}")
        return 0

    result = run_corrective_reextract(
        db_path=db_path,
        baseline_prompt_version=PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
        target_prompt_path=PROMPT_PASS2_TRADE_EXAMPLE_V2_PATH,
        target_prompt_version=PROMPT_VERSION_PASS2_TRADE_EXAMPLE_V2,
    )
    run_dir = write_corrective_artifacts(result=result)
    _log.info(
        "corrective_reextract.complete",
        run_dir=str(run_dir),
        chunks=len(result.chunk_records),
        total_cost_usd=result.total_cost_usd,
    )
    print(f"Wrote {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
