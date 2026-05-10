"""Tests for the Pass 2 TradeExample price-rescaling audit."""

from __future__ import annotations

from trading_wiki.extractors.pass2.price_audit import _price_variants


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
