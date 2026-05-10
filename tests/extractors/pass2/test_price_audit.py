"""Tests for the Pass 2 TradeExample price-rescaling audit."""

from __future__ import annotations

import dataclasses
import json
import sqlite3
import subprocess
import sys
from datetime import UTC
from datetime import datetime as _dt
from pathlib import Path
from types import SimpleNamespace
from typing import Any as _Any

import pytest

from trading_wiki.extractors.pass2.price_audit import (
    PriceAuditFinding,
    _chunk_contains_value,
    _classify_severity,
    _normalize_chunk_text,
    _price_variants,
    audit_trade_example_prices,
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


def _make_te_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": 1,
        "source_chunk_id": 10,
        "entry_price": None,
        "stop_price": None,
        "target_price": None,
        "exit_price": None,
    }
    base.update(overrides)
    return base


def _make_chunk_row(chunk_id: int = 10, content_id: int = 2, text: str = "") -> dict[str, object]:
    return {"id": chunk_id, "content_id": content_id, "text": text}


def test_audit_empty_te_rows_returns_empty() -> None:
    assert audit_trade_example_prices(te_rows=[], chunk_rows=[]) == []


def test_audit_te_with_all_null_prices_produces_no_findings() -> None:
    te_rows = [_make_te_row()]
    chunk_rows = [_make_chunk_row(text="some unrelated transcript")]
    assert audit_trade_example_prices(te_rows=te_rows, chunk_rows=chunk_rows) == []


def test_audit_literal_present_emits_info_finding() -> None:
    te_rows = [_make_te_row(entry_price=295.0)]
    chunk_rows = [_make_chunk_row(text="I entered NVDA at 295 yesterday")]
    findings = audit_trade_example_prices(te_rows=te_rows, chunk_rows=chunk_rows)
    assert len(findings) == 1
    assert findings[0].severity == "info"
    assert findings[0].field == "entry_price"
    assert findings[0].literal_present is True


def test_audit_rescaled_only_emits_high_finding() -> None:
    # Extracted 2.95 but chunk only says 295 — silent rescaling
    te_rows = [_make_te_row(entry_price=2.95)]
    chunk_rows = [_make_chunk_row(text="I entered at 295")]
    findings = audit_trade_example_prices(te_rows=te_rows, chunk_rows=chunk_rows)
    assert len(findings) == 1
    assert findings[0].severity == "high"
    assert findings[0].x100_present is True
    assert findings[0].literal_present is False


def test_audit_value_not_in_chunk_emits_medium_finding() -> None:
    te_rows = [_make_te_row(entry_price=42.0)]
    chunk_rows = [_make_chunk_row(text="I had a great trade")]
    findings = audit_trade_example_prices(te_rows=te_rows, chunk_rows=chunk_rows)
    assert len(findings) == 1
    assert findings[0].severity == "medium"


def test_audit_self_correction_is_info_not_high() -> None:
    """Chunk contains both '295' (x100 of extracted 2.95) and '2.95' literal."""
    te_rows = [_make_te_row(entry_price=2.95)]
    chunk_rows = [_make_chunk_row(text="I got in at 295 — I mean 2.95, sorry")]
    findings = audit_trade_example_prices(te_rows=te_rows, chunk_rows=chunk_rows)
    assert len(findings) == 1
    assert findings[0].severity == "info"
    assert findings[0].literal_present is True


def test_audit_missing_chunk_id_is_logged_and_skipped() -> None:
    """TE row references a chunk_id with no matching chunk row → skip."""
    te_rows = [_make_te_row(source_chunk_id=999, entry_price=42.0)]
    chunk_rows = [_make_chunk_row(chunk_id=10, text="hi")]
    findings = audit_trade_example_prices(te_rows=te_rows, chunk_rows=chunk_rows)
    assert findings == []


def test_audit_multiple_price_fields_in_one_row() -> None:
    te_rows = [
        _make_te_row(entry_price=295.0, stop_price=290.0, target_price=310.0, exit_price=305.0)
    ]
    chunk_rows = [_make_chunk_row(text="entered 295 stopped 290 target 310 exited 305")]
    findings = audit_trade_example_prices(te_rows=te_rows, chunk_rows=chunk_rows)
    assert len(findings) == 4
    assert all(f.severity == "info" for f in findings)


def test_chunk_does_not_match_integer_prefix_of_decimal_price() -> None:
    """295 should not match inside 295.25 — different prices."""
    assert _chunk_contains_value("entered at 295.25", "295") is False


def test_chunk_does_not_match_integer_prefix_with_trailing_decimal_zero() -> None:
    """295 should not match inside 295.0 — different precision."""
    assert _chunk_contains_value("entered at 295.0", "295") is False


def test_chunk_still_matches_value_followed_by_sentence_period() -> None:
    """295 should still match in 'I bought at 295.' (sentence end)."""
    assert _chunk_contains_value("I bought at 295.", "295") is True


def test_chunk_does_not_match_decimal_inside_longer_decimal() -> None:
    """2.95 should not match inside 2.95.0 — unusual but defensible."""
    assert _chunk_contains_value("price 2.95.0", "2.95") is False


def _seed_audit_corpus(db_path: Path) -> None:
    """Seed a minimal DB with one chunk and one trade_example row."""
    from trading_wiki.config import (
        PROMPT_VERSION_PASS1,
        PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
    )
    from trading_wiki.core.db import apply_migrations, save_content_record
    from trading_wiki.handlers.base import ContentRecord, Segment

    apply_migrations(db_path)
    cid = save_content_record(
        db_path,
        ContentRecord(
            source_type="local_video",
            source_id="vid:audit",
            title="audit",
            raw_text="t",
            created_at=_dt(2026, 5, 10, tzinfo=UTC),
            ingested_at=_dt(2026, 5, 10, tzinfo=UTC),
            segments=[Segment(seq=0, text="hi", start_seconds=0.0, end_seconds=1.0)],
        ),
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO chunks
            (content_id, seq, start_seg_seq, end_seg_seq, label, confidence,
             summary, text, prompt_version, created_at)
            VALUES (?, 0, 0, 0, 'example', 'high', 's',
                    'I entered NVDA at 295 yesterday', ?, '2026-05-10')
            """,
            (cid, PROMPT_VERSION_PASS1),
        )
        chunk_id = conn.execute("SELECT id FROM chunks").fetchone()[0]
        conn.execute(
            """
            INSERT INTO trade_examples
            (source_chunk_id, ticker, direction, instrument_type,
             trade_date, entry_price, stop_price, target_price, exit_price,
             entry_description, exit_description, outcome_text,
             outcome_classification, lessons, confidence,
             prompt_version, created_at)
            VALUES (?, 'NVDA', 'long', 'stock',
                    NULL, 295.0, NULL, NULL, NULL,
                    'long at 295', 'flat', 'ok',
                    'scratch', NULL, 'high',
                    ?, '2026-05-10')
            """,
            (chunk_id, PROMPT_VERSION_PASS2_TRADE_EXAMPLE),
        )
        conn.commit()


def test_cli_writes_artifacts_for_all(tmp_path: Path, monkeypatch: _Any) -> None:
    from trading_wiki.extractors.pass2.price_audit import main

    db_path = tmp_path / "research.db"
    _seed_audit_corpus(db_path)

    monkeypatch.setattr(
        "trading_wiki.extractors.pass2.price_audit.Settings",
        lambda: SimpleNamespace(db_path=db_path),
    )
    monkeypatch.setattr(
        "trading_wiki.extractors.pass2.price_audit._OUTPUT_BASE_DIR",
        tmp_path / "out",
    )

    rc = main(["--all"])
    assert rc == 0
    out_runs = list((tmp_path / "out").iterdir())
    assert len(out_runs) == 1
    run_dir = out_runs[0]
    payload = json.loads((run_dir / "findings.json").read_text(encoding="utf-8"))
    # Single info finding: 295.0 matches "I entered NVDA at 295"
    assert payload["counts"]["info"] == 1
    assert payload["counts"]["high"] == 0


def test_write_audit_artifacts_writes_json_and_md(tmp_path: Path) -> None:
    from trading_wiki.extractors.pass2.price_audit import (
        PriceAuditFinding,
        write_audit_artifacts,
    )

    findings = [
        PriceAuditFinding(
            te_id=1,
            chunk_id=10,
            content_id=2,
            field="entry_price",
            extracted_value=2.95,
            literal_present=False,
            x10_present=False,
            div10_present=False,
            x100_present=True,
            div100_present=False,
            severity="high",
        ),
        PriceAuditFinding(
            te_id=2,
            chunk_id=11,
            content_id=2,
            field="entry_price",
            extracted_value=295.0,
            literal_present=True,
            x10_present=False,
            div10_present=False,
            x100_present=False,
            div100_present=False,
            severity="info",
        ),
    ]
    chunk_texts = {10: "I entered at 295 yesterday", 11: "Long NVDA at 295"}

    run_dir = write_audit_artifacts(
        findings=findings,
        chunk_texts=chunk_texts,
        output_base_dir=tmp_path,
    )

    assert run_dir.is_dir()
    assert run_dir.parent == tmp_path

    findings_json = json.loads((run_dir / "findings.json").read_text(encoding="utf-8"))
    assert findings_json["counts"] == {"high": 1, "medium": 0, "info": 1, "total": 2}
    assert len(findings_json["findings"]) == 2

    md = (run_dir / "findings.md").read_text(encoding="utf-8")
    # High and medium are surfaced in the report; info is summarized but not
    # rendered with chunk excerpts.
    assert "## High severity" in md
    assert "te_id=1" in md
    assert "## Medium severity" not in md  # 0 medium findings
    # Chunk excerpt for the high finding should be in the report
    assert "entered at 295" in md


def test_price_audit_module_help_exits_zero() -> None:
    """`python -m trading_wiki.extractors.pass2.price_audit --help` exits 0."""
    proc = subprocess.run(
        [sys.executable, "-m", "trading_wiki.extractors.pass2.price_audit", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "price_audit" in proc.stdout
    assert "--content-id" in proc.stdout
    assert "--all" in proc.stdout
