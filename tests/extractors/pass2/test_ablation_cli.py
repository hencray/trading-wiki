"""Tests for the contamination-ablation CLI."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from trading_wiki.config import PROMPT_VERSION_PASS1
from trading_wiki.core.db import apply_migrations, save_content_record
from trading_wiki.core.llm import UsageRecord
from trading_wiki.extractors.pass2.ablation import main
from trading_wiki.handlers.base import ContentRecord, Segment


def _seed_minimal_corpus(db_path: Path) -> None:
    apply_migrations(db_path)
    cid = save_content_record(
        db_path,
        ContentRecord(
            source_type="local_video",
            source_id="vid:cli",
            title="cli",
            raw_text="t",
            created_at=datetime(2026, 5, 10, tzinfo=UTC),
            ingested_at=datetime(2026, 5, 10, tzinfo=UTC),
            segments=[Segment(seq=0, text="hi", start_seconds=0.0, end_seconds=1.0)],
        ),
    )
    rows = [
        ("example", 0),
        ("concept", 1),
        ("qa", 2),
        ("strategy", 3),
        ("noise", 4),
    ]
    with sqlite3.connect(db_path) as conn:
        for label, seq in rows:
            conn.execute(
                """
                INSERT INTO chunks
                (content_id, seq, start_seg_seq, end_seg_seq, label, confidence,
                 summary, text, prompt_version, created_at)
                VALUES (?, ?, 0, 0, ?, 'high', 's', 'tx', ?, '2026-05-10')
                """,
                (cid, seq, label, PROMPT_VERSION_PASS1),
            )
        conn.commit()


def test_cli_defaults_and_writes_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "research.db"
    _seed_minimal_corpus(db_path)

    # Stub Settings to point at the test DB
    from types import SimpleNamespace

    monkeypatch.setattr(
        "trading_wiki.extractors.pass2.ablation.Settings",
        lambda: SimpleNamespace(db_path=db_path),
    )
    monkeypatch.setattr(
        "trading_wiki.extractors.pass2.ablation._OUTPUT_BASE_DIR",
        tmp_path / "out",
    )

    # Stub extractor functions to return empty entity lists with zero usage
    def _stub_te(**kwargs: Any) -> Any:
        return (
            [],
            UsageRecord(model="m", input_tokens=0, output_tokens=0, cost_estimate_usd=0.0),
        )

    def _stub_concept(**kwargs: Any) -> Any:
        return (
            [],
            UsageRecord(model="m", input_tokens=0, output_tokens=0, cost_estimate_usd=0.0),
        )

    monkeypatch.setattr(
        "trading_wiki.extractors.pass2.ablation.extract_trade_examples_for_chunk",
        _stub_te,
    )
    monkeypatch.setattr(
        "trading_wiki.extractors.pass2.ablation.extract_concepts_for_chunk",
        _stub_concept,
    )

    rc = main(
        [
            "--n-priming-te",
            "1",
            "--n-priming-concept",
            "2",
            "--n-routing",
            "2",
            "--seed",
            "7",
        ]
    )

    assert rc == 0
    out_runs = list((tmp_path / "out").iterdir())
    assert len(out_runs) == 1
    run_dir = out_runs[0]
    assert (run_dir / "config.json").is_file()
    assert (run_dir / "priming_diff.md").is_file()
    assert (run_dir / "routing_audit.md").is_file()
    assert (run_dir / "summary.md").is_file()

    cfg = json.loads((run_dir / "config.json").read_text())
    assert cfg["seed"] == 7
    assert cfg["n_priming_te"] == 1
