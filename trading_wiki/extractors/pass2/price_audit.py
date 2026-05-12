"""Phase 2A v0.3 — Pass 2 TradeExample price-rescaling audit.

Spec: docs/superpowers/specs/2026-05-10-pass2-te-price-audit-design.md
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import structlog

from trading_wiki.config import PROMPT_VERSION_PASS2_TRADE_EXAMPLE
from trading_wiki.core.db import list_content_summaries, list_trade_examples_for_content
from trading_wiki.core.secrets import Settings


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


_OUTPUT_BASE_DIR = Path("data/audits")


def _excerpt(text: str, value_str: str, *, radius: int = 200) -> str | None:
    """Return ±``radius`` chars around the first occurrence of ``value_str``
    in ``text`` (digit-boundary-aware). Returns None if not found.
    """
    pattern = rf"(?<![\d.]){re.escape(value_str)}(?![\d])(?!\.\d)"
    match = re.search(pattern, text)
    if match is None:
        return None
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


def _count_by_severity(findings: list[PriceAuditFinding]) -> dict[str, int]:
    counts: dict[str, int] = {"high": 0, "medium": 0, "info": 0}
    for f in findings:
        counts[f.severity] += 1
    counts["total"] = len(findings)
    return counts


def _render_findings_md(
    findings: list[PriceAuditFinding],
    chunk_texts: dict[int, str],
    *,
    prompt_version: str,
) -> str:
    counts = _count_by_severity(findings)
    lines = [
        "# TE Price Audit Findings",
        "",
        f"- prompt_version: `{prompt_version}`",
        f"- High: {counts['high']}",
        f"- Medium: {counts['medium']}",
        f"- Info (literal-present, not flagged): {counts['info']}",
        f"- Total audited: {counts['total']}",
        "",
    ]
    for severity in ("high", "medium"):
        flagged = [f for f in findings if f.severity == severity]
        if not flagged:
            continue
        lines.append(f"## {severity.capitalize()} severity")
        lines.append("")
        for f in flagged:
            lines.append(
                f"- **te_id={f.te_id}** chunk_id={f.chunk_id} "
                f"content_id={f.content_id} field=`{f.field}` "
                f"extracted_value=`{f.extracted_value}`"
            )
            variants_present = {
                "literal": f.literal_present,
                "x10": f.x10_present,
                "div10": f.div10_present,
                "x100": f.x100_present,
                "div100": f.div100_present,
            }
            present = ", ".join(k for k, v in variants_present.items() if v) or "(none)"
            lines.append(f"  - variants present in chunk: {present}")
            text = chunk_texts.get(f.chunk_id, "")
            normalized = _normalize_chunk_text(text)
            for variant_name, value_set in (
                ("literal", _format_value(f.extracted_value)),
                ("x10", _format_value(f.extracted_value * 10)),
                ("div10", _format_value(f.extracted_value / 10)),
                ("x100", _format_value(f.extracted_value * 100)),
                ("div100", _format_value(f.extracted_value / 100)),
            ):
                excerpt: str | None = None
                for variant in value_set:
                    excerpt = _excerpt(normalized, variant)
                    if excerpt is not None:
                        lines.append(f"  - excerpt around `{variant}` ({variant_name}):")
                        lines.append(f"    > {excerpt}")
                        break
            lines.append("")
    return "\n".join(lines)


def write_audit_artifacts(
    *,
    findings: list[PriceAuditFinding],
    chunk_texts: dict[int, str],
    output_base_dir: Path | None = None,
    prompt_version: str = PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
) -> Path:
    """Write ``findings.json`` and ``findings.md`` to a fresh run directory.

    Returns the run directory path. ``prompt_version`` is recorded in both
    artifacts so future readers can tell v1 audits from v2 audits.
    """
    base = output_base_dir if output_base_dir is not None else _OUTPUT_BASE_DIR
    run_id = datetime.now().isoformat(timespec="seconds").replace(":", "-")
    run_dir = base / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "run_id": run_id,
        "prompt_version": prompt_version,
        "counts": _count_by_severity(findings),
        "findings": [
            {
                "te_id": f.te_id,
                "chunk_id": f.chunk_id,
                "content_id": f.content_id,
                "field": f.field,
                "extracted_value": f.extracted_value,
                "literal_present": f.literal_present,
                "x10_present": f.x10_present,
                "div10_present": f.div10_present,
                "x100_present": f.x100_present,
                "div100_present": f.div100_present,
                "severity": f.severity,
            }
            for f in findings
        ],
    }
    (run_dir / "findings.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (run_dir / "findings.md").write_text(
        _render_findings_md(findings, chunk_texts, prompt_version=prompt_version),
        encoding="utf-8",
    )
    return run_dir


def _load_te_rows_and_chunks(
    db_path: Path,
    *,
    content_id: int | None,
    prompt_version: str = PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load TE rows at the given ``prompt_version`` plus all chunks they
    reference. If ``content_id`` is None, load across all content rows.

    ``prompt_version`` defaults to the locked production v1 version so
    existing callers and tests are unaffected.
    """
    te_rows: list[dict[str, Any]] = []
    if content_id is not None:
        content_ids = [content_id]
    else:
        content_ids = [int(c["id"]) for c in list_content_summaries(db_path)]
    for cid in content_ids:
        for row in list_trade_examples_for_content(db_path, content_id=cid):
            if row["prompt_version"] != prompt_version:
                continue
            te_rows.append(dict(row))

    chunk_ids = {int(r["source_chunk_id"]) for r in te_rows}
    chunk_rows: list[dict[str, Any]] = []
    if chunk_ids:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            placeholders = ",".join("?" * len(chunk_ids))
            cursor = conn.execute(
                f"SELECT id, content_id, text FROM chunks WHERE id IN ({placeholders})",
                tuple(chunk_ids),
            )
            chunk_rows = [dict(row) for row in cursor.fetchall()]
    return te_rows, chunk_rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m trading_wiki.extractors.pass2.price_audit",
        description="Audit Pass 2 TradeExample rows for silent price rescaling.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--content-id", type=int, default=None)
    group.add_argument("--all", action="store_true")
    parser.add_argument(
        "--prompt-version",
        type=str,
        default=PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
        help=(
            "TradeExample prompt_version to audit. Defaults to the locked v1 production version."
        ),
    )
    args = parser.parse_args(argv)

    db_path = Settings().db_path
    te_rows, chunk_rows = _load_te_rows_and_chunks(
        db_path,
        content_id=args.content_id if not args.all else None,
        prompt_version=args.prompt_version,
    )

    findings = audit_trade_example_prices(te_rows=te_rows, chunk_rows=chunk_rows)
    chunk_texts = {int(c["id"]): str(c["text"]) for c in chunk_rows}
    run_dir = write_audit_artifacts(
        findings=findings,
        chunk_texts=chunk_texts,
        prompt_version=args.prompt_version,
    )

    _log.info(
        "price_audit.complete",
        run_dir=str(run_dir),
        prompt_version=args.prompt_version,
        counts=_count_by_severity(findings),
    )
    print(f"Wrote {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
