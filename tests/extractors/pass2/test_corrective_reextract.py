"""Tests for the Phase 2A v0.3 corrective slice driver."""

from __future__ import annotations

import sqlite3
from datetime import UTC
from datetime import datetime as _dt
from pathlib import Path

import pytest


def _seed_baseline_corpus(db_path: Path) -> list[int]:
    """Seed a minimal DB with three chunks: two routed to TradeExample with v1
    TE rows (one of which also has a v2 row from a prior partial re-extract),
    and one routed to qa with no TE rows. Returns the chunk_ids that should be
    discovered as baseline candidates."""
    from trading_wiki.config import (
        PROMPT_VERSION_PASS1,
        PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
        PROMPT_VERSION_PASS2_TRADE_EXAMPLE_V2,
    )
    from trading_wiki.core.db import apply_migrations, save_content_record
    from trading_wiki.handlers.base import ContentRecord, Segment

    apply_migrations(db_path)
    cid = save_content_record(
        db_path,
        ContentRecord(
            source_type="local_video",
            source_id="vid:fixture",
            title="fixture",
            raw_text="t",
            created_at=_dt(2026, 5, 11, tzinfo=UTC),
            ingested_at=_dt(2026, 5, 11, tzinfo=UTC),
            segments=[Segment(seq=0, text="hi", start_seconds=0.0, end_seconds=1.0)],
        ),
    )
    with sqlite3.connect(db_path) as conn:
        for seq, label in enumerate(("example", "example", "qa")):
            conn.execute(
                """
                INSERT INTO chunks
                (content_id, seq, start_seg_seq, end_seg_seq, label, confidence,
                 summary, text, prompt_version, created_at)
                VALUES (?, ?, 0, 0, ?, 'high', 's', 'text', ?, '2026-05-11')
                """,
                (cid, seq, label, PROMPT_VERSION_PASS1),
            )
        chunk_ids = [int(r[0]) for r in conn.execute("SELECT id FROM chunks ORDER BY id")]
        # Chunk 0: 1 v1 TE row (baseline candidate)
        # Chunk 1: 1 v1 + 1 v2 TE row (baseline candidate — v1 row still present)
        # Chunk 2: routed to qa, no TE rows (NOT a baseline candidate)
        for chunk_id, version in (
            (chunk_ids[0], PROMPT_VERSION_PASS2_TRADE_EXAMPLE),
            (chunk_ids[1], PROMPT_VERSION_PASS2_TRADE_EXAMPLE),
            (chunk_ids[1], PROMPT_VERSION_PASS2_TRADE_EXAMPLE_V2),
        ):
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
                (chunk_id, version),
            )
        conn.commit()
    return chunk_ids[:2]


def test_discover_baseline_chunk_ids_returns_deduped_v1_chunks(
    tmp_path: Path,
) -> None:
    """_discover_baseline_chunk_ids must return unique chunk_ids that have at
    least one v1 TE row, regardless of whether v2 rows exist for the same
    chunk."""
    from trading_wiki.config import PROMPT_VERSION_PASS2_TRADE_EXAMPLE
    from trading_wiki.extractors.pass2.corrective_reextract import (
        _discover_baseline_chunk_ids,
    )

    db_path = tmp_path / "research.db"
    expected = sorted(_seed_baseline_corpus(db_path))

    got = _discover_baseline_chunk_ids(db_path, prompt_version=PROMPT_VERSION_PASS2_TRADE_EXAMPLE)
    assert got == expected


def test_run_corrective_reextract_calls_extractor_per_chunk_and_aggregates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_corrective_reextract iterates the baseline chunk ids and aggregates
    one ChunkRecord per chunk with v1_count, v2_count, v2_entities, cost."""
    from trading_wiki.config import (
        PROMPT_PASS2_TRADE_EXAMPLE_V2_PATH,
        PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
        PROMPT_VERSION_PASS2_TRADE_EXAMPLE_V2,
    )
    from trading_wiki.core.llm import UsageRecord
    from trading_wiki.extractors.pass2 import trade_example as te_mod
    from trading_wiki.extractors.pass2.corrective_reextract import (
        run_corrective_reextract,
    )
    from trading_wiki.extractors.pass2.trade_example import TradeExample

    db_path = tmp_path / "research.db"
    baseline_chunk_ids = _seed_baseline_corpus(db_path)

    fake_entity = TradeExample(
        ticker="NVDA",
        direction="long",
        instrument_type="stock",
        entry_price=2.95,
        entry_description="long at 2.95",
        exit_description="flat",
        outcome_text="ok",
        confidence="high",
    )
    fake_usage = UsageRecord(
        model="claude-sonnet-4-6",
        input_tokens=100,
        output_tokens=50,
        cost_estimate_usd=0.01,
    )

    from typing import Any as _Any

    calls: list[dict[str, _Any]] = []

    def fake_extract(
        *,
        chunk_id: int,
        db_path: Path,
        prompt_path: Path,
        prompt_version: str,
        persist: bool,
    ) -> tuple[list[TradeExample], UsageRecord]:
        calls.append(
            {
                "chunk_id": chunk_id,
                "prompt_path": prompt_path,
                "prompt_version": prompt_version,
                "persist": persist,
            }
        )
        return [fake_entity], fake_usage

    monkeypatch.setattr(te_mod, "extract_trade_examples_for_chunk", fake_extract)

    result = run_corrective_reextract(
        db_path=db_path,
        baseline_prompt_version=PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
        target_prompt_path=PROMPT_PASS2_TRADE_EXAMPLE_V2_PATH,
        target_prompt_version=PROMPT_VERSION_PASS2_TRADE_EXAMPLE_V2,
    )

    # Both baseline chunks were processed; the qa chunk (no TE rows) skipped.
    assert sorted(c["chunk_id"] for c in calls) == sorted(baseline_chunk_ids)
    for c in calls:
        assert c["prompt_path"] == PROMPT_PASS2_TRADE_EXAMPLE_V2_PATH
        assert c["prompt_version"] == PROMPT_VERSION_PASS2_TRADE_EXAMPLE_V2
        assert c["persist"] is True

    # Per-chunk records aggregated correctly.
    assert len(result.chunk_records) == 2
    for record in result.chunk_records:
        assert record.v1_count == 1
        assert record.v2_count == 1
        assert record.cost_usd == 0.01
        assert len(record.v2_entities) == 1
        assert record.v2_entities[0]["ticker"] == "NVDA"

    assert result.total_cost_usd == pytest.approx(0.02)
    assert result.run_id  # ISO timestamp; presence-only check
    assert result.baseline_prompt_version == PROMPT_VERSION_PASS2_TRADE_EXAMPLE
    assert result.target_prompt_version == PROMPT_VERSION_PASS2_TRADE_EXAMPLE_V2


def test_write_corrective_artifacts_writes_json_and_md(tmp_path: Path) -> None:
    """write_corrective_artifacts writes summary.json + summary.md under
    ``<base>/<run_id>/`` with the expected fields."""
    import json

    from trading_wiki.extractors.pass2.corrective_reextract import (
        ChunkRecord,
        RunResult,
        write_corrective_artifacts,
    )

    result = RunResult(
        run_id="2026-05-11T10-00-00",
        baseline_prompt_version="pass2-trade-example-v1",
        target_prompt_version="pass2-trade-example-v2",
        chunk_records=[
            ChunkRecord(
                chunk_id=12,
                v1_count=1,
                v2_count=1,
                v2_entities=[
                    {
                        "ticker": "NVDA",
                        "direction": "long",
                        "trade_date": None,
                        "entry_price": 12.50,
                        "stop_price": None,
                        "target_price": 14.45,
                        "exit_price": None,
                    }
                ],
                cost_usd=0.03,
            ),
            ChunkRecord(
                chunk_id=74,
                v1_count=1,
                v2_count=0,
                v2_entities=[],
                cost_usd=0.02,
            ),
        ],
        total_cost_usd=0.05,
    )

    run_dir = write_corrective_artifacts(result=result, output_base_dir=tmp_path)
    assert run_dir.parent == tmp_path
    assert run_dir.name == "2026-05-11T10-00-00"

    payload = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert payload["run_id"] == "2026-05-11T10-00-00"
    assert payload["baseline_prompt_version"] == "pass2-trade-example-v1"
    assert payload["target_prompt_version"] == "pass2-trade-example-v2"
    assert payload["total_cost_usd"] == 0.05
    assert len(payload["chunk_records"]) == 2
    assert payload["chunk_records"][0]["chunk_id"] == 12
    assert payload["chunk_records"][1]["v2_count"] == 0

    md = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "# Corrective Re-extract Summary" in md
    assert "baseline: `pass2-trade-example-v1`" in md
    assert "target: `pass2-trade-example-v2`" in md
    assert "Total cost: $0.05" in md
    assert "chunk_id=12" in md
    assert "v1=1 → v2=1" in md
    assert "entry_price=12.5" in md  # 12.50 stringifies as 12.5
    assert "chunk_id=74" in md
    assert "v1=1 → v2=0" in md
