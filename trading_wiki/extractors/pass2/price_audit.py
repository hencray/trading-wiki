"""Phase 2A v0.3 — Pass 2 TradeExample price-rescaling audit.

Spec: docs/superpowers/specs/2026-05-10-pass2-te-price-audit-design.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

import structlog


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


_THOUSANDS_COMMA = re.compile(r"(?<=\d),(?=\d)")


def _normalize_chunk_text(text: str) -> str:
    """Lowercase, strip ``$``, and remove commas between digits.

    Used so chunk-text scans can match extracted prices regardless of unit
    decoration. Commas not between digits (e.g., ``"Tuesday, March 5"``) are
    preserved so we don't garble prose.
    """
    text = text.lower()
    text = text.replace("$", "")
    text = _THOUSANDS_COMMA.sub("", text)
    return text


def _chunk_contains_value(normalized_text: str, value_str: str) -> bool:
    """Return True iff ``value_str`` appears in ``normalized_text`` with no
    adjacent digit or decimal-point characters on either side.

    The lookarounds ensure ``"295"`` does NOT match inside ``"2950"`` and
    ``"2.95"`` does NOT match inside ``"2.957"``. ``normalized_text`` should
    already have been lowercased and stripped of ``$`` / thousands commas via
    :func:`_normalize_chunk_text`.
    """
    pattern = rf"(?<![\d.]){re.escape(value_str)}(?![\d])(?!\.\d)"
    return re.search(pattern, normalized_text) is not None


Severity = Literal["high", "medium", "info"]
PriceField = Literal["entry_price", "stop_price", "target_price", "exit_price"]


@dataclass(frozen=True)
class PriceAuditFinding:
    """One audit row: one extracted price vs. its source chunk."""

    te_id: int
    chunk_id: int
    content_id: int
    field: PriceField
    extracted_value: float
    literal_present: bool
    x10_present: bool
    div10_present: bool
    x100_present: bool
    div100_present: bool
    severity: Severity


def _classify_severity(
    *,
    literal_present: bool,
    x10_present: bool,
    div10_present: bool,
    x100_present: bool,
    div100_present: bool,
) -> Severity:
    """Classify a finding.

    - ``info`` — literal present (extraction matches the chunk; no flag)
    - ``high`` — literal absent AND at least one rescaled variant present
      (likely silent rescaling)
    - ``medium`` — literal absent AND no rescaled variant present
      (extracted value not in chunk at all)
    """
    if literal_present:
        return "info"
    if x10_present or div10_present or x100_present or div100_present:
        return "high"
    return "medium"


_log = structlog.get_logger(__name__)

_PRICE_FIELDS: tuple[PriceField, ...] = (
    "entry_price",
    "stop_price",
    "target_price",
    "exit_price",
)


def audit_trade_example_prices(
    *,
    te_rows: list[dict[str, Any]],
    chunk_rows: list[dict[str, Any]],
) -> list[PriceAuditFinding]:
    """Audit a list of TradeExample rows for silent price rescaling.

    For each non-NULL price field on each TE row, generate the literal +
    rescaled variants and check which ones appear in the source chunk text
    (digit-boundary-aware). Emit one ``PriceAuditFinding`` per audited
    price field. Rows whose ``source_chunk_id`` has no matching row in
    ``chunk_rows`` are logged and skipped.

    ``chunk_rows`` must include ``id``, ``content_id``, and ``text``.
    """
    chunk_by_id: dict[int, dict[str, Any]] = {int(c["id"]): c for c in chunk_rows}
    findings: list[PriceAuditFinding] = []

    for te in te_rows:
        chunk_id = int(te["source_chunk_id"])
        chunk = chunk_by_id.get(chunk_id)
        if chunk is None:
            _log.warning(
                "price_audit.chunk_missing",
                te_id=int(te["id"]),
                source_chunk_id=chunk_id,
            )
            continue
        normalized = _normalize_chunk_text(str(chunk["text"]))

        for field in _PRICE_FIELDS:
            value = te.get(field)
            if value is None:
                continue
            literal = _format_value(float(value))
            literal_present = any(_chunk_contains_value(normalized, v) for v in literal)
            x10 = _format_value(float(value) * 10)
            x10_present = any(_chunk_contains_value(normalized, v) for v in x10)
            div10 = _format_value(float(value) / 10)
            div10_present = any(_chunk_contains_value(normalized, v) for v in div10)
            x100 = _format_value(float(value) * 100)
            x100_present = any(_chunk_contains_value(normalized, v) for v in x100)
            div100 = _format_value(float(value) / 100)
            div100_present = any(_chunk_contains_value(normalized, v) for v in div100)

            severity = _classify_severity(
                literal_present=literal_present,
                x10_present=x10_present,
                div10_present=div10_present,
                x100_present=x100_present,
                div100_present=div100_present,
            )
            findings.append(
                PriceAuditFinding(
                    te_id=int(te["id"]),
                    chunk_id=chunk_id,
                    content_id=int(chunk["content_id"]),
                    field=field,
                    extracted_value=float(value),
                    literal_present=literal_present,
                    x10_present=x10_present,
                    div10_present=div10_present,
                    x100_present=x100_present,
                    div100_present=div100_present,
                    severity=severity,
                )
            )
    return findings
