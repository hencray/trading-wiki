"""Tests for the artifact writer."""

from __future__ import annotations

import json
from pathlib import Path

from trading_wiki.extractors.pass2.ablation import (
    AblationConfig,
    EntityDiff,
    PrimingDiff,
    RoutingAudit,
    RoutingAuditEntry,
    write_run_artifacts,
)


def _example_config(run_id: str = "2026-05-10T18-32-00") -> AblationConfig:
    return AblationConfig(
        run_id=run_id,
        seed=42,
        n_priming_te=10,
        n_priming_concept=10,
        n_routing=10,
        sampled_chunk_ids={"te_priming": [1, 2], "concept_priming": [3], "routing": [4]},
        total_cost_usd=2.50,
        total_input_tokens=1000,
        total_output_tokens=500,
    )


def _example_priming_diff() -> PrimingDiff:
    return PrimingDiff(
        chunk_id=13,
        content_id=1,
        chunk_label="example",
        chunk_seq=4,
        baseline_count=1,
        blind_count=1,
        overall_verdict="identical",
        entity_diffs=[
            EntityDiff(
                verdict="identical",
                baseline={"ticker": "NVDA"},
                blind={"ticker": "NVDA"},
                changed_fields=[],
            )
        ],
    )


def _example_audit() -> RoutingAudit:
    return RoutingAudit(
        entries=[
            RoutingAuditEntry(
                chunk_id=10,
                content_id=1,
                chunk_label="qa",
                chunk_text_excerpt="Generic chunk text for fixture",
                proposed_entities=[{"ticker": "XTST", "direction": "long"}],
            )
        ],
        total_chunks_audited=10,
    )


def test_write_run_artifacts_creates_four_files(tmp_path: Path) -> None:
    run_dir = tmp_path / "data" / "ablation" / "2026-05-10T18-32-00"
    write_run_artifacts(
        run_dir=run_dir,
        config=_example_config(),
        te_priming_diffs=[_example_priming_diff()],
        concept_priming_diffs=[],
        routing_audit=_example_audit(),
    )

    assert (run_dir / "config.json").is_file()
    assert (run_dir / "priming_diff.md").is_file()
    assert (run_dir / "routing_audit.md").is_file()
    assert (run_dir / "summary.md").is_file()


def test_config_json_round_trips(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    config = _example_config()
    write_run_artifacts(
        run_dir=run_dir,
        config=config,
        te_priming_diffs=[],
        concept_priming_diffs=[],
        routing_audit=RoutingAudit(entries=[], total_chunks_audited=0),
    )

    loaded = json.loads((run_dir / "config.json").read_text())
    assert loaded["seed"] == 42
    assert loaded["sampled_chunk_ids"]["te_priming"] == [1, 2]


def test_priming_diff_md_contains_chunk_section(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    write_run_artifacts(
        run_dir=run_dir,
        config=_example_config(),
        te_priming_diffs=[_example_priming_diff()],
        concept_priming_diffs=[],
        routing_audit=RoutingAudit(entries=[], total_chunks_audited=0),
    )

    body = (run_dir / "priming_diff.md").read_text()
    assert "chunk_id=13" in body
    assert "label=example" in body
    assert "identical" in body


def test_routing_audit_md_records_empty_result(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    write_run_artifacts(
        run_dir=run_dir,
        config=_example_config(),
        te_priming_diffs=[],
        concept_priming_diffs=[],
        routing_audit=RoutingAudit(entries=[], total_chunks_audited=10),
    )

    body = (run_dir / "routing_audit.md").read_text()
    assert "No routing misses found" in body
    assert "n=10" in body
