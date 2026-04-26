import pytest
from pydantic import ValidationError

from trading_wiki.extractors.pass2.trade_example import (
    TradeExample,
    TradeExampleOutput,
)


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
