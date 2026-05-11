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


def test_cli_arms_te_skips_concept_and_routing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When --arms te is passed, only the TE-priming arm should call its
    extractor; Concept and routing arms must be skipped entirely.
    """
    db_path = tmp_path / "research.db"
    _seed_minimal_corpus(db_path)

    from types import SimpleNamespace

    monkeypatch.setattr(
        "trading_wiki.extractors.pass2.ablation.Settings",
        lambda: SimpleNamespace(db_path=db_path),
    )
    monkeypatch.setattr(
        "trading_wiki.extractors.pass2.ablation._OUTPUT_BASE_DIR",
        tmp_path / "out",
    )

    te_calls = 0
    concept_calls = 0

    def _stub_te(**kwargs: Any) -> Any:
        nonlocal te_calls
        te_calls += 1
        return ([], UsageRecord(model="m", input_tokens=0, output_tokens=0, cost_estimate_usd=0.0))

    def _stub_concept(**kwargs: Any) -> Any:
        nonlocal concept_calls
        concept_calls += 1
        return ([], UsageRecord(model="m", input_tokens=0, output_tokens=0, cost_estimate_usd=0.0))

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
            "1",
            "--n-routing",
            "1",
            "--seed",
            "7",
            "--arms",
            "te",
        ]
    )

    assert rc == 0
    # Only the TE-priming arm runs; routing arm (which also uses TE extractor)
    # is skipped.
    assert te_calls == 1
    assert concept_calls == 0


def test_cli_arms_defaults_preserve_three_arm_behavior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Existing zero-flag invocation still runs all three arms."""
    db_path = tmp_path / "research.db"
    _seed_minimal_corpus(db_path)

    from types import SimpleNamespace

    monkeypatch.setattr(
        "trading_wiki.extractors.pass2.ablation.Settings",
        lambda: SimpleNamespace(db_path=db_path),
    )
    monkeypatch.setattr(
        "trading_wiki.extractors.pass2.ablation._OUTPUT_BASE_DIR",
        tmp_path / "out",
    )

    te_calls = 0
    concept_calls = 0

    def _stub_te(**kwargs: Any) -> Any:
        nonlocal te_calls
        te_calls += 1
        return ([], UsageRecord(model="m", input_tokens=0, output_tokens=0, cost_estimate_usd=0.0))

    def _stub_concept(**kwargs: Any) -> Any:
        nonlocal concept_calls
        concept_calls += 1
        return ([], UsageRecord(model="m", input_tokens=0, output_tokens=0, cost_estimate_usd=0.0))

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
            "1",
            "--n-routing",
            "1",
            "--seed",
            "7",
        ]
    )

    assert rc == 0
    # TE priming (1) + routing (1) = 2 TE calls; concept priming (1) = 1 concept
    assert te_calls == 2
    assert concept_calls == 1


def test_cli_te_test_prompt_path_overrides_blind_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When --te-test-prompt-path is passed, the TE extractor is called with
    that path instead of the default blind path.
    """
    db_path = tmp_path / "research.db"
    _seed_minimal_corpus(db_path)

    from types import SimpleNamespace

    monkeypatch.setattr(
        "trading_wiki.extractors.pass2.ablation.Settings",
        lambda: SimpleNamespace(db_path=db_path),
    )
    monkeypatch.setattr(
        "trading_wiki.extractors.pass2.ablation._OUTPUT_BASE_DIR",
        tmp_path / "out",
    )

    captured_kwargs: list[dict[str, Any]] = []

    def _capture_te(**kwargs: Any) -> Any:
        captured_kwargs.append(dict(kwargs))
        return ([], UsageRecord(model="m", input_tokens=0, output_tokens=0, cost_estimate_usd=0.0))

    monkeypatch.setattr(
        "trading_wiki.extractors.pass2.ablation.extract_trade_examples_for_chunk",
        _capture_te,
    )

    custom_path = tmp_path / "custom_te_prompt.md"
    custom_path.write_text("custom prompt body")

    rc = main(
        [
            "--n-priming-te",
            "1",
            "--n-priming-concept",
            "0",
            "--n-routing",
            "0",
            "--seed",
            "7",
            "--arms",
            "te",
            "--te-test-prompt-path",
            str(custom_path),
            "--te-test-prompt-version",
            "pass2-trade-example-v2",
        ]
    )

    assert rc == 0
    assert len(captured_kwargs) == 1
    assert captured_kwargs[0]["prompt_path"] == custom_path
    assert captured_kwargs[0]["prompt_version"] == "pass2-trade-example-v2"


def test_cli_default_test_prompts_are_blind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No --*-test-prompt-* flags → harness uses blind paths/versions."""
    from trading_wiki.config import (
        PROMPT_PASS2_TRADE_EXAMPLE_BLIND_PATH,
        PROMPT_VERSION_PASS2_TRADE_EXAMPLE_BLIND,
    )

    db_path = tmp_path / "research.db"
    _seed_minimal_corpus(db_path)

    from types import SimpleNamespace

    monkeypatch.setattr(
        "trading_wiki.extractors.pass2.ablation.Settings",
        lambda: SimpleNamespace(db_path=db_path),
    )
    monkeypatch.setattr(
        "trading_wiki.extractors.pass2.ablation._OUTPUT_BASE_DIR",
        tmp_path / "out",
    )

    captured_kwargs: list[dict[str, Any]] = []

    def _capture_te(**kwargs: Any) -> Any:
        captured_kwargs.append(dict(kwargs))
        return ([], UsageRecord(model="m", input_tokens=0, output_tokens=0, cost_estimate_usd=0.0))

    monkeypatch.setattr(
        "trading_wiki.extractors.pass2.ablation.extract_trade_examples_for_chunk",
        _capture_te,
    )

    rc = main(
        [
            "--n-priming-te",
            "1",
            "--n-priming-concept",
            "0",
            "--n-routing",
            "0",
            "--seed",
            "7",
            "--arms",
            "te",
        ]
    )

    assert rc == 0
    assert len(captured_kwargs) == 1
    assert captured_kwargs[0]["prompt_path"] == PROMPT_PASS2_TRADE_EXAMPLE_BLIND_PATH
    assert captured_kwargs[0]["prompt_version"] == PROMPT_VERSION_PASS2_TRADE_EXAMPLE_BLIND
