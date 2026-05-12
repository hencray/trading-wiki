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
from pathlib import Path

import structlog

_log = structlog.get_logger(__name__)


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
