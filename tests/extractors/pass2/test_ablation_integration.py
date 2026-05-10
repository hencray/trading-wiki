"""Integration test for the contamination-ablation CLI end-to-end.

Mocks ``call_structured`` at the extractor-module level (not the higher
``extract_*_for_chunk`` level) so the full extractor code path — including
prompt resolution, persist=False idempotency bypass, and entity parsing — runs.

Run with: ``uv run pytest -m integration``
Skipped by default (deselected by ``-m not integration`` in addopts).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from trading_wiki.config import PROMPT_VERSION_PASS1
from trading_wiki.core.db import apply_migrations, save_content_record
from trading_wiki.core.llm import UsageRecord
from trading_wiki.extractors.pass2.ablation import main
from trading_wiki.handlers.base import ContentRecord, Segment


def _seed_corpus(db_path: Path) -> None:
    """Seed one content record and four chunks (one per arm plus routing)."""
    apply_migrations(db_path)
    cid = save_content_record(
        db_path,
        ContentRecord(
            source_type="local_video",
            source_id="vid:integ",
            title="integ",
            raw_text="t",
            created_at=datetime(2026, 5, 10, tzinfo=UTC),
            ingested_at=datetime(2026, 5, 10, tzinfo=UTC),
            segments=[Segment(seq=0, text="full transcript", start_seconds=0.0, end_seconds=1.0)],
        ),
    )
    # Include one chunk from each arm:
    #   "example"  -> TE priming pool
    #   "concept"  -> Concept priming pool
    #   "qa"       -> also Concept priming pool (but n_priming_concept=1 picks 1)
    #   "strategy" -> routing pool (ROUTING_LABELS)
    rows = [
        ("example", 0, "trade-example chunk text"),
        ("concept", 1, "concept chunk text"),
        ("qa", 2, "qa chunk text"),
        ("strategy", 3, "strategy chunk text"),
    ]
    with sqlite3.connect(db_path) as conn:
        for label, seq, text in rows:
            conn.execute(
                """
                INSERT INTO chunks
                (content_id, seq, start_seg_seq, end_seg_seq, label, confidence,
                 summary, text, prompt_version, created_at)
                VALUES (?, ?, 0, 0, ?, 'high', 's', ?, ?, '2026-05-10')
                """,
                (cid, seq, label, text, PROMPT_VERSION_PASS1),
            )
        conn.commit()


def _make_call_structured_stub(
    te_payload: list[dict[str, Any]],
    concept_payload: list[dict[str, Any]],
) -> Any:
    """Return a stub with ``call_structured``'s keyword-only signature.

    Dispatches on ``schema.__name__`` to return entity-type-appropriate data.
    """

    def _stub(**kwargs: Any) -> Any:
        schema_name = kwargs["schema"].__name__
        if schema_name == "TradeExampleOutput":
            payload = {"entities": te_payload}
        else:
            payload = {"entities": concept_payload}
        output = kwargs["schema"].model_validate(payload)
        usage = UsageRecord(model="stub", input_tokens=10, output_tokens=5, cost_estimate_usd=0.001)
        return (output, usage, [])

    return _stub


@pytest.mark.integration
def test_ablation_cli_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: seeds DB, mocks LLM, runs CLI, asserts all four artifacts."""
    db_path = tmp_path / "research.db"
    _seed_corpus(db_path)

    monkeypatch.setattr(
        "trading_wiki.extractors.pass2.ablation.Settings",
        lambda: SimpleNamespace(db_path=db_path),
    )
    monkeypatch.setattr(
        "trading_wiki.extractors.pass2.ablation._OUTPUT_BASE_DIR",
        tmp_path / "out",
    )

    stub = _make_call_structured_stub(
        te_payload=[
            {
                "ticker": "NVDA",
                "direction": "long",
                "instrument_type": "stock",
                "entry_description": "broke pivot",
                "exit_description": "took profit",
                "outcome_text": "won",
                "confidence": "high",
            }
        ],
        concept_payload=[
            {
                "term": "pivot",
                "definition": "average of high, low, and close",
                "related_terms": [],
                "confidence": "high",
            }
        ],
    )
    monkeypatch.setattr("trading_wiki.extractors.pass2.trade_example.call_structured", stub)
    monkeypatch.setattr("trading_wiki.extractors.pass2.concept.call_structured", stub)

    # n_priming_te=1  → 1 TE call (example pool has 1 chunk)
    # n_priming_concept=1 → 1 Concept call (concept+qa pool; 1 sampled)
    # n_routing=1     → 1 TE blind call over strategy chunk
    # Total: 3 stub calls x 10 input_tokens = 30
    rc = main(
        ["--n-priming-te", "1", "--n-priming-concept", "1", "--n-routing", "1", "--seed", "1"]
    )

    assert rc == 0

    # Exactly one run directory written
    runs = list((tmp_path / "out").iterdir())
    assert len(runs) == 1
    run_dir = runs[0]

    # All four artifact files must exist
    assert (run_dir / "config.json").is_file()
    assert (run_dir / "priming_diff.md").is_file()
    assert (run_dir / "routing_audit.md").is_file()
    assert (run_dir / "summary.md").is_file()

    # config.json content checks
    cfg = json.loads((run_dir / "config.json").read_text())
    assert cfg["seed"] == 1
    assert cfg["total_input_tokens"] == 30  # 3 stub calls x 10 input tokens

    # priming_diff.md content checks — both extractor names rendered
    priming = (run_dir / "priming_diff.md").read_text()
    assert "trade_example" in priming
    assert "concept" in priming

    # routing_audit.md content check
    audit = (run_dir / "routing_audit.md").read_text()
    assert "routing audit" in audit.lower()
