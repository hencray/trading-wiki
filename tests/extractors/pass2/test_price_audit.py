"""Tests for the Pass 2 TradeExample price-rescaling audit."""

from __future__ import annotations

import dataclasses

import pytest

from trading_wiki.extractors.pass2.price_audit import (
    _chunk_contains_value,
    _normalize_chunk_text,
    _price_variants,
)


def test_price_variants_integer_value_has_both_int_and_decimal_forms() -> None:
    variants = _price_variants(295.0)
    # literal
    assert "295" in variants
    assert "295.0" in variants
    # x10
    assert "2950" in variants
    assert "2950.0" in variants
    # /10 (non-integer result → no .0 form)
    assert "29.5" in variants
    assert "29.50" not in variants
    # x100
    assert "29500" in variants
    assert "29500.0" in variants
    # /100 (non-integer)
    assert "2.95" in variants


def test_price_variants_non_integer_value_no_trailing_zero_form() -> None:
    variants = _price_variants(850.25)
    assert "850.25" in variants
    # No "850.25.0" or "850.2500" nonsense
    assert all("." not in v or len(v.split(".")[-1]) <= 2 for v in variants)
    # x10 = 8502.5 still has ≤ 2 decimals → included
    assert "8502.5" in variants
    # /100 = 8.5025 has 4 decimals → excluded
    assert "8.5025" not in variants
    assert "8.50" not in variants  # we don't collapse


def test_price_variants_value_above_three_digit_minimum() -> None:
    """A 4-digit price (e.g., 1200) generates expected variants."""
    variants = _price_variants(1200.0)
    assert "1200" in variants
    assert "1200.0" in variants
    assert "120" in variants  # /10
    assert "12" in variants  # /100
    assert "12000" in variants  # x10


def test_price_variants_returns_set_of_strings() -> None:
    variants = _price_variants(50.0)
    assert isinstance(variants, set)
    assert all(isinstance(v, str) for v in variants)


def test_price_variants_zero_returns_empty_set() -> None:
    """The value <= 0 guard in _format_value should produce an empty variant set."""
    assert _price_variants(0.0) == set()


def test_price_variants_three_decimal_value_excludes_rounded_variants() -> None:
    """Variants that would require >2 decimal places must be excluded — not rounded.

    Without this guard, _format_value(8.5025) silently returned {"8.5"}, which
    is a spurious low-precision variant of 850.25 / 100.
    """
    variants = _price_variants(850.25)
    # The ÷100 result 8.5025 needs 4 decimal places → must be excluded
    assert "8.5" not in variants
    assert "8.50" not in variants
    assert "8.5025" not in variants


def test_normalize_chunk_strips_dollar_signs() -> None:
    assert _normalize_chunk_text("Entered at $295.") == "entered at 295."


def test_normalize_chunk_strips_thousands_commas_between_digits() -> None:
    assert _normalize_chunk_text("Cost was $1,200") == "cost was 1200"


def test_normalize_chunk_preserves_commas_in_prose() -> None:
    """Commas not between digits stay (e.g., 'Tuesday, March 5')."""
    assert _normalize_chunk_text("Tuesday, March 5") == "tuesday, march 5"


def test_normalize_chunk_lowercases() -> None:
    assert _normalize_chunk_text("NVDA Long") == "nvda long"


def test_chunk_contains_exact_value() -> None:
    assert _chunk_contains_value("entered at 295.", "295") is True


def test_chunk_does_not_match_value_inside_larger_number() -> None:
    """295 should not match inside 2950."""
    assert _chunk_contains_value("entered at 2950.", "295") is False


def test_chunk_does_not_match_decimal_prefix_of_longer_number() -> None:
    """2.95 should not match inside 2.957."""
    assert _chunk_contains_value("entered at 2.957", "2.95") is False


def test_chunk_match_at_string_boundaries() -> None:
    """Value at the very start or end of the string should match."""
    assert _chunk_contains_value("295", "295") is True
    assert _chunk_contains_value("price 295", "295") is True
    assert _chunk_contains_value("295 dollars", "295") is True


def test_classify_severity_literal_present_is_info() -> None:
    from trading_wiki.extractors.pass2.price_audit import _classify_severity

    assert (
        _classify_severity(
            literal_present=True,
            x10_present=False,
            div10_present=False,
            x100_present=False,
            div100_present=False,
        )
        == "info"
    )


def test_classify_severity_literal_present_overrides_rescaled() -> None:
    """Both present (speaker self-correction) → info, not high."""
    from trading_wiki.extractors.pass2.price_audit import _classify_severity

    assert (
        _classify_severity(
            literal_present=True,
            x10_present=False,
            div10_present=False,
            x100_present=True,
            div100_present=False,
        )
        == "info"
    )


def test_classify_severity_only_rescaled_is_high() -> None:
    from trading_wiki.extractors.pass2.price_audit import _classify_severity

    assert (
        _classify_severity(
            literal_present=False,
            x10_present=False,
            div10_present=False,
            x100_present=False,
            div100_present=True,
        )
        == "high"
    )


def test_classify_severity_none_present_is_medium() -> None:
    from trading_wiki.extractors.pass2.price_audit import _classify_severity

    assert (
        _classify_severity(
            literal_present=False,
            x10_present=False,
            div10_present=False,
            x100_present=False,
            div100_present=False,
        )
        == "medium"
    )


def test_price_audit_finding_is_frozen_dataclass() -> None:
    from trading_wiki.extractors.pass2.price_audit import PriceAuditFinding

    finding = PriceAuditFinding(
        te_id=1,
        chunk_id=10,
        content_id=2,
        field="entry_price",
        extracted_value=295.0,
        literal_present=True,
        x10_present=False,
        div10_present=False,
        x100_present=False,
        div100_present=False,
        severity="info",
    )
    assert dataclasses.is_dataclass(finding)
    with pytest.raises(dataclasses.FrozenInstanceError):
        finding.te_id = 99  # type: ignore[misc]
