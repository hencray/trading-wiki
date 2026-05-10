"""Tests for the priming-diff builder."""

from __future__ import annotations

from typing import Any

from trading_wiki.extractors.pass2.ablation import build_priming_diff


def _chunk(chunk_id: int = 1, label: str = "example") -> dict[str, Any]:
    return {
        "id": chunk_id,
        "content_id": 7,
        "seq": 3,
        "label": label,
    }


def test_diff_identical_when_both_lists_match() -> None:
    e = {"ticker": "NVDA", "direction": "long", "entry_price": 100.0}
    diff = build_priming_diff(
        chunk=_chunk(),
        baseline=[e],
        blind=[e],
        match_key="ticker",
    )
    assert diff.overall_verdict == "identical"
    assert diff.entity_diffs[0].verdict == "identical"
    assert diff.entity_diffs[0].changed_fields == []


def test_diff_field_changed_when_paired_entity_differs() -> None:
    diff = build_priming_diff(
        chunk=_chunk(),
        baseline=[{"ticker": "NVDA", "entry_price": 100.0}],
        blind=[{"ticker": "NVDA", "entry_price": 101.0}],
        match_key="ticker",
    )
    assert diff.overall_verdict == "field_changed"
    assert diff.entity_diffs[0].verdict == "field_changed"
    assert diff.entity_diffs[0].changed_fields == ["entry_price"]


def test_diff_count_changed_when_blind_adds_entity() -> None:
    diff = build_priming_diff(
        chunk=_chunk(),
        baseline=[{"ticker": "NVDA"}],
        blind=[{"ticker": "NVDA"}, {"ticker": "AAPL"}],
        match_key="ticker",
    )
    assert diff.overall_verdict == "count_changed"
    verdicts = sorted(d.verdict for d in diff.entity_diffs)
    assert verdicts == ["added", "identical"]


def test_diff_count_changed_when_blind_removes_entity() -> None:
    diff = build_priming_diff(
        chunk=_chunk(),
        baseline=[{"ticker": "NVDA"}, {"ticker": "AAPL"}],
        blind=[{"ticker": "NVDA"}],
        match_key="ticker",
    )
    assert diff.overall_verdict == "count_changed"
    verdicts = sorted(d.verdict for d in diff.entity_diffs)
    assert verdicts == ["identical", "removed"]


def test_diff_handles_both_empty() -> None:
    diff = build_priming_diff(
        chunk=_chunk(),
        baseline=[],
        blind=[],
        match_key="ticker",
    )
    assert diff.overall_verdict == "identical"
    assert diff.baseline_count == 0
    assert diff.blind_count == 0
    assert diff.entity_diffs == []


def test_diff_same_count_different_entities_is_not_identical() -> None:
    """Baseline and blind with same count but disjoint entity sets must not report identical."""
    diff = build_priming_diff(
        chunk=_chunk(),
        baseline=[{"ticker": "NVDA"}],
        blind=[{"ticker": "AAPL"}],
        match_key="ticker",
    )
    # Counts equal (1 == 1) but entities are completely different.
    # Reporting 'identical' here would be a silent miss — the harness would
    # claim the prompt had no effect when in fact it swapped the entire output.
    assert diff.overall_verdict != "identical"
    verdicts = sorted(d.verdict for d in diff.entity_diffs)
    assert verdicts == ["added", "removed"]


def test_diff_strips_db_fields_from_baseline_rows() -> None:
    """build_priming_diff must strip DB-internal fields even when baseline is passed
    directly without pre-stripping (defense against caller-bypass)."""
    diff = build_priming_diff(
        chunk=_chunk(),
        baseline=[
            {
                "id": 5,
                "source_chunk_id": 9,
                "prompt_version": "pass2-trade-example-v1",
                "created_at": "2026-04-26T08:34:52",
                "ticker": "NVDA",
                "direction": "long",
            }
        ],
        blind=[{"ticker": "NVDA", "direction": "long"}],
        match_key="ticker",
    )
    assert diff.overall_verdict == "identical"
    assert diff.entity_diffs[0].verdict == "identical"
    assert diff.entity_diffs[0].changed_fields == []
