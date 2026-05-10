"""Phase 2A v0.3 — Pass 2 TradeExample price-rescaling audit.

Spec: docs/superpowers/specs/2026-05-10-pass2-te-price-audit-design.md
"""

from __future__ import annotations


def _format_value(value: float) -> set[str]:
    """Return string representations for a numeric value.

    Integer values produce both ``"<int>"`` and ``"<int>.0"`` forms; non-integer
    values produce only the canonical decimal form (no trailing-zero collapse,
    no extra precision). Values whose canonical decimal form needs more than 2
    decimal places are excluded so we don't generate variants that wouldn't
    appear as spoken prices (e.g., ÷100 of 850.25 = 8.5025 must not produce
    a rounded "8.5").
    """
    if value <= 0:
        return set()
    if value == int(value):
        return {str(int(value)), f"{int(value)}.0"}
    if round(value, 2) != value:
        return set()
    formatted = f"{value:.2f}".rstrip("0").rstrip(".")
    return {formatted}


def _price_variants(value: float) -> set[str]:
    """Generate literal + rescaled variants of a price value as strings.

    Variants include literal, x10, /10, x100, /100. Each is formatted under the
    same int-vs-decimal rules. Variants that would have >2 decimal places are
    skipped (stock prices effectively never do).
    """
    variants: set[str] = set()
    for factor in (1.0, 10.0, 0.1, 100.0, 0.01):
        variants |= _format_value(value * factor)
    return variants
