"""Opt-in integration test: real Anthropic API call against a real transcript.

Run with: ``uv run pytest -m integration``
Skipped by default. Requires:
  - ANTHROPIC_API_KEY set in .env
  - At least one transcribed v1 source video in the configured DB
  - The CONTENT_ID env var pointing at it (e.g. CONTENT_ID=7)
"""

import os
from pathlib import Path

import pytest

from trading_wiki.core.secrets import Settings
from trading_wiki.extractors.pass1 import (
    Pass1Chunk,
    Pass1Output,
    extract,
    validate_coverage,
)


@pytest.mark.integration
def test_pass1_against_real_transcript():
    content_id_env = os.environ.get("CONTENT_ID")
    if not content_id_env:
        pytest.skip("CONTENT_ID env var not set; pointing at no transcript.")
    content_id = int(content_id_env)
    db_path = Settings().db_path
    if not Path(db_path).exists():
        pytest.skip(f"DB at {db_path} does not exist.")

    rows = extract(content_id=content_id)

    assert len(rows) >= 1, "Pass 1 returned zero chunks."
    for row in rows:
        summary = row["summary"]
        assert isinstance(summary, str)
        assert summary.strip(), f"chunk seq={row['seq']} has empty summary"

    output = Pass1Output(
        chunks=[
            Pass1Chunk(
                seq=row["seq"],
                start_seg_seq=row["start_seg_seq"],
                end_seg_seq=row["end_seg_seq"],
                label=row["label"],
                confidence=row["confidence"],
                summary=row["summary"],
            )
            for row in rows
        ]
    )

    import sqlite3

    with sqlite3.connect(db_path) as conn:
        seg_count = conn.execute(
            "SELECT COUNT(*) FROM segments WHERE content_id = ?",
            (content_id,),
        ).fetchone()[0]
    validate_coverage(output, segment_count=seg_count)
    assert 1 <= len(rows) <= seg_count
