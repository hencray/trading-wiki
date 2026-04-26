from pathlib import Path

from trading_wiki.review.findings import REVIEWS_DIR, findings_path_for


def test_findings_path_for_default_dir():
    assert findings_path_for(7) == Path("docs/superpowers/reviews/content7.md")


def test_findings_path_for_custom_base_dir(tmp_path):
    assert findings_path_for(42, base_dir=tmp_path) == tmp_path / "content42.md"


def test_reviews_dir_constant():
    assert Path("docs/superpowers/reviews") == REVIEWS_DIR
