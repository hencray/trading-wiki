"""Test that DB-internal fields are stripped from baseline rows before diffing."""

from __future__ import annotations

from trading_wiki.extractors.pass2.ablation import _strip_db_fields


def test_strip_db_fields_removes_known_internal_fields() -> None:
    row = {
        "id": 5,
        "source_chunk_id": 9,
        "prompt_version": "pass2-trade-example-v1",
        "created_at": "2026-04-26T08:34:52",
        "ticker": "TSLA",
        "direction": "long",
        "entry_price": 331.0,
    }
    stripped = _strip_db_fields(row)
    assert stripped == {
        "ticker": "TSLA",
        "direction": "long",
        "entry_price": 331.0,
    }


def test_strip_db_fields_leaves_extraction_only_rows_unchanged() -> None:
    """Rows from blind extractor (no DB-internal fields) should be unchanged."""
    row = {
        "ticker": "NVDA",
        "direction": "long",
        "entry_price": 100.0,
        "confidence": "high",
    }
    assert _strip_db_fields(row) == row
