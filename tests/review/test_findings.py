from datetime import UTC, datetime
from pathlib import Path

import pytest

from trading_wiki.review.findings import (
    REVIEWS_DIR,
    Finding,
    append_finding,
    findings_path_for,
    read_findings,
)


def test_findings_path_for_default_dir():
    assert findings_path_for(7) == Path("docs/superpowers/reviews/content7.md")


def test_findings_path_for_custom_base_dir(tmp_path):
    assert findings_path_for(42, base_dir=tmp_path) == tmp_path / "content42.md"


def test_reviews_dir_constant():
    assert Path("docs/superpowers/reviews") == REVIEWS_DIR


def test_read_findings_missing_file_returns_empty_list(tmp_path):
    assert read_findings(tmp_path / "nope.md") == []


def test_read_findings_empty_file_returns_empty_list(tmp_path):
    p = tmp_path / "f.md"
    p.write_text("# Review — content_id=1\n\n")
    assert read_findings(p) == []


def test_read_findings_parses_single_entry(tmp_path):
    p = tmp_path / "f.md"
    p.write_text(
        "# Review — content_id=2\n"
        "\n"
        "## item:trade_example:42\n"
        "- status: accept\n"
        "- chunk_id: 17\n"
        "- chunk_label: example\n"
        "- prompt_version: pass2-trade-example-v1\n"
        "- reviewed_at: 2026-04-26T14:32:01Z\n"
        "- notes: prices match transcript\n"
    )
    findings = read_findings(p)
    assert findings == [
        Finding(
            entity_type="trade_example",
            entity_id=42,
            status="accept",
            chunk_id=17,
            chunk_label="example",
            prompt_version="pass2-trade-example-v1",
            reviewed_at=datetime(2026, 4, 26, 14, 32, 1, tzinfo=UTC),
            notes="prices match transcript",
        )
    ]


def test_read_findings_duplicate_entity_id_last_wins(tmp_path):
    p = tmp_path / "f.md"
    p.write_text(
        "# Review — content_id=2\n\n"
        "## item:concept:9\n"
        "- status: needs_fix\n"
        "- chunk_id: 23\n"
        "- chunk_label: concept\n"
        "- prompt_version: pass2-concept-v1\n"
        "- reviewed_at: 2026-04-26T14:00:00Z\n"
        "- notes: first pass\n"
        "\n"
        "## item:concept:9\n"
        "- status: accept\n"
        "- chunk_id: 23\n"
        "- chunk_label: concept\n"
        "- prompt_version: pass2-concept-v1\n"
        "- reviewed_at: 2026-04-26T15:00:00Z\n"
        "- notes: second pass\n"
    )
    findings = read_findings(p)
    assert len(findings) == 1
    assert findings[0].status == "accept"
    assert findings[0].notes == "second pass"


def test_read_findings_malformed_block_raises(tmp_path):
    p = tmp_path / "f.md"
    p.write_text(
        "# Review — content_id=2\n\n## item:trade_example:42\n- status: accept\n- chunk_id: 17\n"
    )
    with pytest.raises(ValueError, match="item:trade_example:42"):
        read_findings(p)


def test_append_finding_creates_file_with_header(tmp_path):
    p = tmp_path / "subdir" / "content5.md"
    f = Finding(
        entity_type="trade_example",
        entity_id=1,
        status="accept",
        chunk_id=10,
        chunk_label="example",
        prompt_version="pass2-trade-example-v1",
        reviewed_at=datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
        notes="ok",
    )
    append_finding(p, f, content_id=5)
    text = p.read_text()
    assert text.startswith("# Review — content_id=5\n")
    assert "## item:trade_example:1" in text
    assert "- notes: ok" in text


def test_append_finding_does_not_duplicate_header(tmp_path):
    p = tmp_path / "content5.md"
    f1 = Finding(
        "trade_example",
        1,
        "accept",
        10,
        "example",
        "pass2-trade-example-v1",
        datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
        "a",
    )
    f2 = Finding(
        "concept",
        2,
        "skip",
        11,
        "concept",
        "pass2-concept-v1",
        datetime(2026, 4, 26, 12, 1, 0, tzinfo=UTC),
        "b",
    )
    append_finding(p, f1, content_id=5)
    append_finding(p, f2, content_id=5)
    text = p.read_text()
    assert text.count("# Review — content_id=5") == 1
    assert "## item:trade_example:1" in text
    assert "## item:concept:2" in text


def test_append_finding_collapses_notes_newlines(tmp_path):
    p = tmp_path / "content5.md"
    f = Finding(
        "trade_example",
        1,
        "accept",
        10,
        "example",
        "pass2-trade-example-v1",
        datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
        "line1\nline2\r\nline3",
    )
    append_finding(p, f, content_id=5)
    text = p.read_text()
    assert "- notes: line1 line2 line3" in text
    assert "line1\nline2" not in text


def test_append_finding_roundtrips_via_read_findings(tmp_path):
    p = tmp_path / "content5.md"
    f = Finding(
        "concept",
        9,
        "needs_fix",
        23,
        "concept",
        "pass2-concept-v1",
        datetime(2026, 4, 26, 14, 35, 12, tzinfo=UTC),
        "definition restates the metaphor",
    )
    append_finding(p, f, content_id=5)
    assert read_findings(p) == [f]
