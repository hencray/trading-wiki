"""Tests for the routing-audit builder."""

from __future__ import annotations

from trading_wiki.extractors.pass2.ablation import build_routing_audit


def test_audit_filters_to_chunks_with_entities() -> None:
    chunks = [
        {"id": 10, "content_id": 1, "label": "qa", "text": "x" * 100, "seq": 0},
        {"id": 11, "content_id": 1, "label": "noise", "text": "y" * 100, "seq": 1},
    ]
    blind_results = {
        10: [{"ticker": "NVDA"}],
        11: [],
    }

    audit = build_routing_audit(non_example_chunks=chunks, blind_results=blind_results)

    assert audit.total_chunks_audited == 2
    assert len(audit.entries) == 1
    assert audit.entries[0].chunk_id == 10
    assert audit.entries[0].proposed_entities == [{"ticker": "NVDA"}]


def test_audit_truncates_chunk_text_excerpt() -> None:
    long_text = "x" * 1000
    chunks = [{"id": 10, "content_id": 1, "label": "qa", "text": long_text, "seq": 0}]
    blind_results = {10: [{"ticker": "NVDA"}]}

    audit = build_routing_audit(non_example_chunks=chunks, blind_results=blind_results)

    # Excerpt is at most 603 chars (600 + "...")
    assert len(audit.entries[0].chunk_text_excerpt) <= 603
    assert audit.entries[0].chunk_text_excerpt.endswith("...")


def test_audit_sorts_entries_by_chunk_id() -> None:
    chunks = [
        {"id": 22, "content_id": 1, "label": "qa", "text": "a", "seq": 0},
        {"id": 11, "content_id": 1, "label": "noise", "text": "b", "seq": 1},
    ]
    blind_results = {22: [{"ticker": "NVDA"}], 11: [{"ticker": "AAPL"}]}

    audit = build_routing_audit(non_example_chunks=chunks, blind_results=blind_results)

    assert [e.chunk_id for e in audit.entries] == [11, 22]


def test_audit_handles_no_misses() -> None:
    chunks = [{"id": 1, "content_id": 1, "label": "qa", "text": "x", "seq": 0}]
    blind_results: dict[int, list[dict[str, object]]] = {1: []}

    audit = build_routing_audit(non_example_chunks=chunks, blind_results=blind_results)

    assert audit.total_chunks_audited == 1
    assert audit.entries == []


def test_audit_handles_missing_chunk_id_in_results() -> None:
    """If a chunk's id isn't a key in blind_results, treat as empty list (no entities)."""
    chunks = [{"id": 1, "content_id": 1, "label": "qa", "text": "x", "seq": 0}]
    blind_results: dict[int, list[dict[str, object]]] = {}

    audit = build_routing_audit(non_example_chunks=chunks, blind_results=blind_results)

    assert audit.total_chunks_audited == 1
    assert audit.entries == []
