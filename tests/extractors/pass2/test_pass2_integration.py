"""Opt-in integration test: real Anthropic API call for Pass 2 against a real chunk set.

Run with: ``uv run pytest -m integration``
Skipped by default. Requires:
  - ANTHROPIC_API_KEY set in .env
  - Pass 1 already run for at least one content_id (default: CONTENT_ID=2,
    the v1 source primary videos from Phase 2A v0.1).
"""

import os
import sqlite3
from pathlib import Path

import pytest

from trading_wiki.config import (
    PASS2_LABEL_ROUTES,
    PROMPT_VERSION_PASS1,
    PROMPT_VERSION_PASS2_CONCEPT,
    PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
)
from trading_wiki.core.secrets import Settings
from trading_wiki.extractors.pass2 import extract


@pytest.mark.integration
def test_pass2_against_real_chunks():
    content_id = int(os.environ.get("CONTENT_ID", "2"))
    db_path = Settings().db_path
    if not Path(db_path).exists():
        pytest.skip(f"DB at {db_path} does not exist.")

    # Sanity: confirm Pass 1 chunks are present for this content_id.
    with sqlite3.connect(db_path) as conn:
        pass1_count = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE content_id = ? AND prompt_version = ?",
            (content_id, PROMPT_VERSION_PASS1),
        ).fetchone()[0]
    if pass1_count == 0:
        pytest.skip(
            f"No Pass 1 chunks for content_id={content_id} at "
            f"prompt_version={PROMPT_VERSION_PASS1}; run Pass 1 first."
        )

    summary = extract(content_id=content_id)

    # Properties that hold for any reasonable LLM output.
    assert summary.chunks_seen >= 1
    assert summary.chunks_routed >= 1, (
        f"Pass 2 routed zero chunks of {summary.chunks_seen}; "
        "Pass 1 may have produced no example/concept/qa chunks."
    )
    assert summary.trade_examples_written + summary.concepts_written >= 1, (
        "Pass 2 wrote zero entities total — at least one routed chunk should "
        "have produced something."
    )
    assert summary.failed_chunks == [], (
        f"Pass 2 had {len(summary.failed_chunks)} per-chunk failures: {summary.failed_chunks!r}"
    )

    # All TradeExample rows came from chunks Pass 1 labeled 'example'.
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        te_rows = conn.execute(
            "SELECT te.id, c.label "
            "FROM trade_examples te JOIN chunks c ON c.id = te.source_chunk_id "
            "WHERE c.content_id = ? AND te.prompt_version = ?",
            (content_id, PROMPT_VERSION_PASS2_TRADE_EXAMPLE),
        ).fetchall()
        for row in te_rows:
            assert row["label"] in PASS2_LABEL_ROUTES["trade_example"], (
                f"TradeExample row {row['id']} came from a chunk labeled "
                f"'{row['label']}' which is not in trade_example route set."
            )

        co_rows = conn.execute(
            "SELECT co.id, c.label "
            "FROM concepts co JOIN chunks c ON c.id = co.source_chunk_id "
            "WHERE c.content_id = ? AND co.prompt_version = ?",
            (content_id, PROMPT_VERSION_PASS2_CONCEPT),
        ).fetchall()
        for row in co_rows:
            assert row["label"] in PASS2_LABEL_ROUTES["concept"], (
                f"Concept row {row['id']} came from a chunk labeled "
                f"'{row['label']}' which is not in concept route set."
            )

        # Required-field non-emptiness sanity.
        for row in conn.execute(
            "SELECT * FROM trade_examples WHERE prompt_version = ?",
            (PROMPT_VERSION_PASS2_TRADE_EXAMPLE,),
        ).fetchall():
            assert row["ticker"]
            assert row["entry_description"]
            assert row["exit_description"]
            assert row["outcome_text"]

        for row in conn.execute(
            "SELECT * FROM concepts WHERE prompt_version = ?",
            (PROMPT_VERSION_PASS2_CONCEPT,),
        ).fetchall():
            assert row["term"]
            assert row["definition"]
            assert len(row["definition"]) >= 10
