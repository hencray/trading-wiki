"""Subprocess CLI tests for the corrective re-extract driver."""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC
from datetime import datetime as _dt
from pathlib import Path


def _seed_dryrun_corpus(db_path: Path) -> list[int]:
    """Seed a DB with 2 baseline TE chunks for dry-run discovery."""
    import sqlite3

    from trading_wiki.config import (
        PROMPT_VERSION_PASS1,
        PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
    )
    from trading_wiki.core.db import apply_migrations, save_content_record
    from trading_wiki.handlers.base import ContentRecord, Segment

    apply_migrations(db_path)
    cid = save_content_record(
        db_path,
        ContentRecord(
            source_type="local_video",
            source_id="vid:dryrun",
            title="dryrun",
            raw_text="t",
            created_at=_dt(2026, 5, 11, tzinfo=UTC),
            ingested_at=_dt(2026, 5, 11, tzinfo=UTC),
            segments=[Segment(seq=0, text="hi", start_seconds=0.0, end_seconds=1.0)],
        ),
    )
    with sqlite3.connect(db_path) as conn:
        for seq in range(2):
            conn.execute(
                """
                INSERT INTO chunks
                (content_id, seq, start_seg_seq, end_seg_seq, label, confidence,
                 summary, text, prompt_version, created_at)
                VALUES (?, ?, 0, 0, 'example', 'high', 's', 'text', ?, '2026-05-11')
                """,
                (cid, seq, PROMPT_VERSION_PASS1),
            )
        chunk_ids = [int(r[0]) for r in conn.execute("SELECT id FROM chunks ORDER BY id")]
        for chunk_id in chunk_ids:
            conn.execute(
                """
                INSERT INTO trade_examples
                (source_chunk_id, ticker, direction, instrument_type,
                 trade_date, entry_price, stop_price, target_price, exit_price,
                 entry_description, exit_description, outcome_text,
                 outcome_classification, lessons, confidence,
                 prompt_version, created_at)
                VALUES (?, 'NVDA', 'long', 'stock',
                        NULL, 295.0, NULL, NULL, NULL,
                        'long at 295', 'flat', 'ok',
                        'scratch', NULL, 'high', ?, '2026-05-11')
                """,
                (chunk_id, PROMPT_VERSION_PASS2_TRADE_EXAMPLE),
            )
        conn.commit()
    return chunk_ids


def test_cli_help_exits_zero() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "trading_wiki.extractors.pass2.corrective_reextract",
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--dry-run" in proc.stdout
    assert "--db-path" in proc.stdout


def test_cli_dry_run_lists_chunks_and_does_not_extract(tmp_path: Path) -> None:
    db_path = tmp_path / "research.db"
    chunk_ids = _seed_dryrun_corpus(db_path)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "trading_wiki.extractors.pass2.corrective_reextract",
            "--db-path",
            str(db_path),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    for chunk_id in chunk_ids:
        assert f"chunk_id={chunk_id}" in proc.stdout
