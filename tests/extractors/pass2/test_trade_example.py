import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from trading_wiki.core.db import (
    apply_migrations,
    load_trade_examples_for_version,
    save_chunks,
    save_content_record,
)
from trading_wiki.core.llm import UsageRecord
from trading_wiki.extractors.pass1 import Pass1Chunk, Pass1Output
from trading_wiki.extractors.pass2.trade_example import (
    TradeExample,
    TradeExampleOutput,
    extract_trade_examples_for_chunk,
)
from trading_wiki.handlers.base import ContentRecord, Segment


class TestTradeExample:
    def test_minimal_required_fields_parse(self):
        ex = TradeExample(
            ticker="NVDA",
            direction="long",
            instrument_type="stock",
            entry_description="entered at 850 after pullback to pivot",
            exit_description="exited at 858 at target",
            outcome_text="won about 11R",
            confidence="high",
        )
        assert ex.ticker == "NVDA"
        assert ex.trade_date is None
        assert ex.entry_price is None
        assert ex.outcome_classification is None
        assert ex.lessons is None

    def test_full_optional_fields_parse(self):
        ex = TradeExample(
            ticker="NVDA",
            direction="long",
            instrument_type="stock",
            trade_date="2026-03-05",
            entry_price=846.0,
            stop_price=843.0,
            target_price=858.0,
            exit_price=857.5,
            entry_description="entered at 846",
            exit_description="exited at 857.5",
            outcome_text="won 11R",
            outcome_classification="won",
            lessons="discipline at the pivot pays",
            confidence="high",
        )
        assert ex.entry_price == 846.0
        assert ex.outcome_classification == "won"

    def test_unknown_direction_rejected(self):
        with pytest.raises(ValidationError):
            TradeExample(
                ticker="NVDA",
                direction="sideways",
                instrument_type="stock",
                entry_description="x",
                exit_description="y",
                outcome_text="z",
                confidence="high",
            )

    def test_unknown_instrument_type_rejected(self):
        with pytest.raises(ValidationError):
            TradeExample(
                ticker="NVDA",
                direction="long",
                instrument_type="commodity",
                entry_description="x",
                exit_description="y",
                outcome_text="z",
                confidence="high",
            )

    def test_unknown_outcome_classification_rejected(self):
        with pytest.raises(ValidationError):
            TradeExample(
                ticker="NVDA",
                direction="long",
                instrument_type="stock",
                entry_description="x",
                exit_description="y",
                outcome_text="z",
                outcome_classification="maybe",
                confidence="high",
            )

    def test_unknown_confidence_rejected(self):
        with pytest.raises(ValidationError):
            TradeExample(
                ticker="NVDA",
                direction="long",
                instrument_type="stock",
                entry_description="x",
                exit_description="y",
                outcome_text="z",
                confidence="mid",
            )

    def test_ticker_over_20_chars_rejected(self):
        with pytest.raises(ValidationError):
            TradeExample(
                ticker="A" * 21,
                direction="long",
                instrument_type="stock",
                entry_description="x",
                exit_description="y",
                outcome_text="z",
                confidence="high",
            )

    def test_entry_description_over_500_chars_rejected(self):
        with pytest.raises(ValidationError):
            TradeExample(
                ticker="NVDA",
                direction="long",
                instrument_type="stock",
                entry_description="x" * 501,
                exit_description="y",
                outcome_text="z",
                confidence="high",
            )

    def test_outcome_text_over_200_chars_rejected(self):
        with pytest.raises(ValidationError):
            TradeExample(
                ticker="NVDA",
                direction="long",
                instrument_type="stock",
                entry_description="x",
                exit_description="y",
                outcome_text="z" * 201,
                confidence="high",
            )

    def test_extra_field_rejected(self):
        # StrictModel forbids extras.
        with pytest.raises(ValidationError):
            TradeExample.model_validate(
                {
                    "ticker": "NVDA",
                    "direction": "long",
                    "instrument_type": "stock",
                    "entry_description": "x",
                    "exit_description": "y",
                    "outcome_text": "z",
                    "confidence": "high",
                    "bogus": "nope",
                }
            )


class TestTradeExampleOutput:
    def test_empty_entities_list_is_valid(self):
        # An "I found no trade examples in this chunk" answer is valid output.
        out = TradeExampleOutput(entities=[])
        assert out.entities == []

    def test_multi_entity_output_parses(self):
        out = TradeExampleOutput(
            entities=[
                TradeExample(
                    ticker="NVDA",
                    direction="long",
                    instrument_type="stock",
                    entry_description="a",
                    exit_description="b",
                    outcome_text="c",
                    confidence="high",
                ),
                TradeExample(
                    ticker="BKSY",
                    direction="short",
                    instrument_type="stock",
                    entry_description="d",
                    exit_description="e",
                    outcome_text="f",
                    confidence="medium",
                ),
            ]
        )
        assert len(out.entities) == 2


# ───────────────────────── extractor tests (LLM mocked) ─────────────────────────


def _seed_chunk(db_path: Path, label: str = "example") -> int:
    """Insert a content + one chunk with the given label. Return chunk_id."""
    record = ContentRecord(
        source_type="test",
        source_id=f"vid-{label}",
        title="t",
        created_at=datetime(2026, 4, 25),
        ingested_at=datetime(2026, 4, 25),
        raw_text="r",
        segments=[Segment(seq=0, text="hello", start_seconds=0.0, end_seconds=1.0)],
    )
    content_id = save_content_record(db_path, record)
    save_chunks(
        db_path,
        content_id=content_id,
        prompt_version="pass1-v1",
        output=Pass1Output(
            chunks=[
                Pass1Chunk(
                    seq=0,
                    start_seg_seq=0,
                    end_seg_seq=0,
                    label=label,
                    confidence="high",
                    summary="x",
                ),
            ]
        ),
    )
    with sqlite3.connect(db_path) as conn:
        chunk_id: int = conn.execute("SELECT id FROM chunks").fetchone()[0]
        return chunk_id


def _stub_usage(
    input_tokens: int = 100,
    output_tokens: int = 50,
    cost: float = 0.001,
) -> UsageRecord:
    return UsageRecord(
        model="claude-sonnet-4-6",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_estimate_usd=cost,
    )


class TestExtractTradeExamplesForChunk:
    @patch("trading_wiki.extractors.pass2.trade_example.call_structured")
    def test_happy_path_writes_rows_and_returns_entities(self, mock_call, tmp_path):
        db_path = tmp_path / "research.db"
        apply_migrations(db_path)
        chunk_id = _seed_chunk(db_path)

        out = TradeExampleOutput(
            entities=[
                TradeExample(
                    ticker="NVDA",
                    direction="long",
                    instrument_type="stock",
                    entry_description="i",
                    exit_description="o",
                    outcome_text="w",
                    confidence="high",
                ),
            ]
        )
        mock_call.return_value = (out, _stub_usage(), [])

        entities, usage = extract_trade_examples_for_chunk(
            chunk_id=chunk_id,
            db_path=db_path,
        )
        assert len(entities) == 1
        assert entities[0].ticker == "NVDA"
        assert usage.input_tokens == 100

        rows = load_trade_examples_for_version(
            db_path,
            source_chunk_id=chunk_id,
            prompt_version="pass2-trade-example-v1",
        )
        assert len(rows) == 1
        assert rows[0]["ticker"] == "NVDA"
        mock_call.assert_called_once()

    @patch("trading_wiki.extractors.pass2.trade_example.call_structured")
    def test_empty_entities_writes_no_rows(self, mock_call, tmp_path):
        db_path = tmp_path / "research.db"
        apply_migrations(db_path)
        chunk_id = _seed_chunk(db_path)

        mock_call.return_value = (TradeExampleOutput(entities=[]), _stub_usage(), [])

        entities, _ = extract_trade_examples_for_chunk(
            chunk_id=chunk_id,
            db_path=db_path,
        )
        assert entities == []
        rows = load_trade_examples_for_version(
            db_path,
            source_chunk_id=chunk_id,
            prompt_version="pass2-trade-example-v1",
        )
        assert rows == []
        mock_call.assert_called_once()

    @patch("trading_wiki.extractors.pass2.trade_example.call_structured")
    def test_idempotent_skips_when_rows_already_exist(self, mock_call, tmp_path):
        db_path = tmp_path / "research.db"
        apply_migrations(db_path)
        chunk_id = _seed_chunk(db_path)

        out = TradeExampleOutput(
            entities=[
                TradeExample(
                    ticker="NVDA",
                    direction="long",
                    instrument_type="stock",
                    entry_description="i",
                    exit_description="o",
                    outcome_text="w",
                    confidence="high",
                ),
            ]
        )
        mock_call.return_value = (out, _stub_usage(), [])

        # First call hits the LLM and writes one row.
        extract_trade_examples_for_chunk(chunk_id=chunk_id, db_path=db_path)
        assert mock_call.call_count == 1

        # Second call short-circuits — no new LLM call, returns the existing entities.
        entities, usage = extract_trade_examples_for_chunk(
            chunk_id=chunk_id,
            db_path=db_path,
        )
        assert mock_call.call_count == 1  # unchanged
        assert len(entities) == 1
        assert entities[0].ticker == "NVDA"
        # Idempotency path returns a zero-cost UsageRecord (no API call).
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.cost_estimate_usd == 0.0

    @patch("trading_wiki.extractors.pass2.trade_example.call_structured")
    def test_idempotent_when_first_run_returned_zero_entities(self, mock_call, tmp_path):
        """Empty-result extraction must still mark the chunk as processed.

        Without this, re-running pass2 on a chunk that legitimately has no trade
        examples re-calls the LLM every time — non-deterministic and cost-leaking.
        """
        db_path = tmp_path / "research.db"
        apply_migrations(db_path)
        chunk_id = _seed_chunk(db_path)

        mock_call.return_value = (TradeExampleOutput(entities=[]), _stub_usage(), [])

        entities, _ = extract_trade_examples_for_chunk(chunk_id=chunk_id, db_path=db_path)
        assert entities == []
        assert mock_call.call_count == 1

        entities, usage = extract_trade_examples_for_chunk(chunk_id=chunk_id, db_path=db_path)
        assert entities == []
        assert mock_call.call_count == 1
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.cost_estimate_usd == 0.0

    @patch("trading_wiki.extractors.pass2.trade_example.call_structured")
    def test_unknown_chunk_id_raises(self, mock_call, tmp_path):
        db_path = tmp_path / "research.db"
        apply_migrations(db_path)

        with pytest.raises(LookupError, match="chunk_id"):
            extract_trade_examples_for_chunk(chunk_id=999, db_path=db_path)
        mock_call.assert_not_called()

    @patch("trading_wiki.extractors.pass2.trade_example.call_structured")
    def test_passes_chunk_text_as_user_message(self, mock_call, tmp_path):
        db_path = tmp_path / "research.db"
        apply_migrations(db_path)
        chunk_id = _seed_chunk(db_path)

        mock_call.return_value = (TradeExampleOutput(entities=[]), _stub_usage(), [])
        extract_trade_examples_for_chunk(chunk_id=chunk_id, db_path=db_path)

        kwargs = mock_call.call_args.kwargs
        assert kwargs["model"] == "claude-sonnet-4-6"
        assert "TradeExample" in kwargs["system"]
        assert kwargs["messages"] == [{"role": "user", "content": "hello"}]
        assert kwargs["schema"] is TradeExampleOutput
