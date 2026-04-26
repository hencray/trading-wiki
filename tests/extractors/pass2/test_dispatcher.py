import subprocess
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from trading_wiki.core.db import (
    apply_migrations,
    save_chunks,
    save_content_record,
)
from trading_wiki.core.llm import UsageRecord
from trading_wiki.extractors.pass1 import Pass1Chunk, Pass1Output
from trading_wiki.extractors.pass2 import Pass2Summary, extract, main
from trading_wiki.extractors.pass2.concept import Concept
from trading_wiki.extractors.pass2.trade_example import TradeExample
from trading_wiki.handlers.base import ContentRecord, Segment


def _seed_content_with_chunks(db_path: Path, labels: list[str]) -> int:
    """Insert one content record + N chunks with the given labels (in order)."""
    record = ContentRecord(
        source_type="test",
        source_id=f"vid-{len(labels)}",
        title="t",
        created_at=datetime(2026, 4, 25),
        ingested_at=datetime(2026, 4, 25),
        raw_text="r",
        segments=[
            Segment(
                seq=i,
                text=f"line {i}",
                start_seconds=float(i),
                end_seconds=float(i + 1),
            )
            for i in range(len(labels))
        ],
    )
    content_id = save_content_record(db_path, record)
    save_chunks(
        db_path,
        content_id=content_id,
        prompt_version="pass1-v1",
        output=Pass1Output(
            chunks=[
                Pass1Chunk(
                    seq=i,
                    start_seg_seq=i,
                    end_seg_seq=i,
                    label=labels[i],
                    confidence="high",
                    summary=f"chunk {i}",
                )
                for i in range(len(labels))
            ]
        ),
    )
    return content_id


def _stub_te_usage() -> UsageRecord:
    return UsageRecord(
        model="claude-sonnet-4-6",
        input_tokens=100,
        output_tokens=50,
        cost_estimate_usd=0.001,
    )


def _stub_co_usage() -> UsageRecord:
    return UsageRecord(
        model="claude-sonnet-4-6",
        input_tokens=80,
        output_tokens=40,
        cost_estimate_usd=0.0008,
    )


def _make_te() -> TradeExample:
    return TradeExample(
        ticker="NVDA",
        direction="long",
        instrument_type="stock",
        entry_description="i",
        exit_description="o",
        outcome_text="w",
        confidence="high",
    )


def _make_concept() -> Concept:
    return Concept(
        term="pivot",
        definition="A pivot is a level.",
        confidence="high",
    )


class TestExtractDispatcher:
    @patch("trading_wiki.extractors.pass2.extract_concepts_for_chunk")
    @patch("trading_wiki.extractors.pass2.extract_trade_examples_for_chunk")
    def test_routes_example_to_trade_example_extractor(self, mock_te, mock_co, tmp_path):
        db_path = tmp_path / "research.db"
        apply_migrations(db_path)
        content_id = _seed_content_with_chunks(db_path, ["example"])

        mock_te.return_value = ([_make_te()], _stub_te_usage())
        mock_co.return_value = ([], _stub_co_usage())

        summary = extract(content_id=content_id, db_path=db_path)
        assert isinstance(summary, Pass2Summary)
        assert summary.chunks_seen == 1
        assert summary.chunks_routed == 1
        assert summary.trade_examples_written == 1
        assert summary.concepts_written == 0
        assert mock_te.call_count == 1
        mock_co.assert_not_called()

    @patch("trading_wiki.extractors.pass2.extract_concepts_for_chunk")
    @patch("trading_wiki.extractors.pass2.extract_trade_examples_for_chunk")
    def test_routes_concept_and_qa_to_concept_extractor(self, mock_te, mock_co, tmp_path):
        db_path = tmp_path / "research.db"
        apply_migrations(db_path)
        content_id = _seed_content_with_chunks(db_path, ["concept", "qa"])

        mock_te.return_value = ([], _stub_te_usage())
        mock_co.return_value = ([_make_concept()], _stub_co_usage())

        summary = extract(content_id=content_id, db_path=db_path)
        assert summary.chunks_seen == 2
        assert summary.chunks_routed == 2
        assert summary.concepts_written == 2  # one per chunk
        assert summary.trade_examples_written == 0
        assert mock_co.call_count == 2
        mock_te.assert_not_called()

    @patch("trading_wiki.extractors.pass2.extract_concepts_for_chunk")
    @patch("trading_wiki.extractors.pass2.extract_trade_examples_for_chunk")
    def test_skips_unrouted_labels(self, mock_te, mock_co, tmp_path):
        db_path = tmp_path / "research.db"
        apply_migrations(db_path)
        content_id = _seed_content_with_chunks(
            db_path,
            ["noise", "psychology", "strategy", "market_commentary"],
        )

        summary = extract(content_id=content_id, db_path=db_path)
        assert summary.chunks_seen == 4
        assert summary.chunks_routed == 0
        assert summary.trade_examples_written == 0
        assert summary.concepts_written == 0
        assert summary.total_input_tokens == 0
        assert summary.total_cost_usd == 0.0
        mock_te.assert_not_called()
        mock_co.assert_not_called()

    @patch("trading_wiki.extractors.pass2.extract_concepts_for_chunk")
    @patch("trading_wiki.extractors.pass2.extract_trade_examples_for_chunk")
    def test_aggregates_usage_across_chunks(self, mock_te, mock_co, tmp_path):
        db_path = tmp_path / "research.db"
        apply_migrations(db_path)
        content_id = _seed_content_with_chunks(db_path, ["example", "example", "concept"])

        mock_te.return_value = ([_make_te()], _stub_te_usage())
        mock_co.return_value = ([_make_concept(), _make_concept()], _stub_co_usage())

        summary = extract(content_id=content_id, db_path=db_path)
        assert summary.chunks_routed == 3
        assert summary.trade_examples_written == 2
        assert summary.concepts_written == 2
        # Token totals: 2 TE calls (100+50 each) + 1 Co call (80+40).
        assert summary.total_input_tokens == 2 * 100 + 80
        assert summary.total_output_tokens == 2 * 50 + 40
        # Cost: 2 * 0.001 + 0.0008.
        assert summary.total_cost_usd == pytest.approx(0.0028, rel=1e-6)

    @patch("trading_wiki.extractors.pass2.extract_concepts_for_chunk")
    @patch("trading_wiki.extractors.pass2.extract_trade_examples_for_chunk")
    def test_per_chunk_resilience_records_failures_continues_processing(
        self, mock_te, mock_co, tmp_path
    ):
        db_path = tmp_path / "research.db"
        apply_migrations(db_path)
        content_id = _seed_content_with_chunks(db_path, ["example", "example", "concept"])

        # Second example chunk's extractor raises.
        mock_te.side_effect = [
            ([_make_te()], _stub_te_usage()),
            RuntimeError("API blew up"),
        ]
        mock_co.return_value = ([_make_concept()], _stub_co_usage())

        summary = extract(content_id=content_id, db_path=db_path)
        assert summary.chunks_routed == 3
        assert summary.trade_examples_written == 1
        assert summary.concepts_written == 1
        assert len(summary.failed_chunks) == 1
        failed_chunk_id, failed_msg = summary.failed_chunks[0]
        assert isinstance(failed_chunk_id, int)
        assert "API blew up" in failed_msg
        # Concept extractor still ran for chunk 3 despite chunk 2's failure.
        assert mock_co.call_count == 1

    def test_raises_when_no_pass1_chunks_for_content(self, tmp_path):
        db_path = tmp_path / "research.db"
        apply_migrations(db_path)

        record = ContentRecord(
            source_type="t",
            source_id="a",
            title="t",
            created_at=datetime(2026, 4, 25),
            ingested_at=datetime(2026, 4, 25),
            raw_text="r",
            segments=[Segment(seq=0, text="x")],
        )
        content_id = save_content_record(db_path, record)
        # NOTE: NO save_chunks call → no Pass 1 output for this content.

        with pytest.raises(RuntimeError, match="run Pass 1 first"):
            extract(content_id=content_id, db_path=db_path)


class TestPass2Cli:
    @patch("trading_wiki.extractors.pass2.extract")
    def test_main_invokes_extract_with_content_id(self, mock_extract):
        mock_extract.return_value = Pass2Summary(
            chunks_seen=5,
            chunks_routed=3,
            trade_examples_written=2,
            concepts_written=4,
            total_input_tokens=300,
            total_output_tokens=150,
            total_cost_usd=0.005,
        )
        exit_code = main(["--content-id", "7"])
        assert exit_code == 0
        mock_extract.assert_called_once_with(content_id=7)

    def test_main_missing_content_id_exits_nonzero(self):
        with pytest.raises(SystemExit) as ei:
            main([])
        assert ei.value.code != 0

    def test_python_m_entry_runs_help(self):
        # `python -m pkg` requires a `__main__.py`; the `if __name__ == "__main__"`
        # guard in `__init__.py` is never reached for package execution.
        result = subprocess.run(
            [sys.executable, "-m", "trading_wiki.extractors.pass2", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"`python -m trading_wiki.extractors.pass2 --help` failed: "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "--content-id" in result.stdout
