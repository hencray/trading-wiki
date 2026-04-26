from datetime import datetime
from pathlib import Path

from trading_wiki.core.db import (
    apply_migrations,
    load_chunks_for_version,
    save_chunks,
    save_concepts,
    save_content_record,
    save_trade_examples,
)
from trading_wiki.extractors.pass1 import Pass1Chunk, Pass1Output
from trading_wiki.extractors.pass2.concept import Concept, ConceptOutput
from trading_wiki.extractors.pass2.trade_example import TradeExample, TradeExampleOutput
from trading_wiki.handlers.base import ContentRecord, Segment
from trading_wiki.review.sampling import sample_items


def _seed(tmp_path: Path) -> tuple[Path, int]:
    db = tmp_path / "t.db"
    apply_migrations(db)
    cid = save_content_record(
        db,
        ContentRecord(
            source_type="local_video",
            source_id="a",
            title="A",
            author=None,
            created_at=datetime(2026, 4, 1),
            ingested_at=datetime(2026, 4, 22),
            raw_text="trade chunk\nconcept chunk",
            segments=[
                Segment(seq=0, text="trade chunk", start_seconds=0.0, end_seconds=1.0),
                Segment(seq=1, text="concept chunk", start_seconds=1.0, end_seconds=2.0),
            ],
        ),
    )
    save_chunks(
        db,
        content_id=cid,
        prompt_version="pass1-v1",
        output=Pass1Output(
            chunks=[
                Pass1Chunk(
                    seq=0,
                    start_seg_seq=0,
                    end_seg_seq=0,
                    label="example",
                    confidence="high",
                    summary="trade",
                ),
                Pass1Chunk(
                    seq=1,
                    start_seg_seq=1,
                    end_seg_seq=1,
                    label="concept",
                    confidence="high",
                    summary="concept",
                ),
            ]
        ),
    )
    chunks = load_chunks_for_version(db, content_id=cid, prompt_version="pass1-v1")
    save_trade_examples(
        db,
        source_chunk_id=chunks[0]["id"],
        prompt_version="pass2-trade-example-v1",
        output=TradeExampleOutput(
            entities=[
                TradeExample(
                    ticker="AAPL",
                    direction="long",
                    instrument_type="stock",
                    trade_date=None,
                    entry_price=100.0,
                    stop_price=99.0,
                    target_price=110.0,
                    exit_price=105.0,
                    entry_description="enter on breakout",
                    exit_description="exit at target",
                    outcome_text="closed at target",
                    outcome_classification="won",
                    lessons=None,
                    confidence="high",
                )
            ]
        ),
    )
    save_concepts(
        db,
        source_chunk_id=chunks[1]["id"],
        prompt_version="pass2-concept-v1",
        output=ConceptOutput(
            entities=[
                Concept(
                    term="VWAP",
                    definition="volume-weighted average price across the session",
                    related_terms=[],
                    confidence="high",
                )
            ]
        ),
    )
    return db, cid


def test_sample_items_mode_all_returns_all_with_chunk_metadata(tmp_path):
    db, cid = _seed(tmp_path)
    items = sample_items(
        db,
        content_id=cid,
        entity_types=["trade_example", "concept"],
        mode="all",
    )
    by_type = {i.entity_type: i for i in items}
    assert set(by_type) == {"trade_example", "concept"}
    assert by_type["trade_example"].chunk_label == "example"
    assert by_type["trade_example"].chunk_text == "trade chunk"
    assert by_type["trade_example"].entity_data["ticker"] == "AAPL"
    assert by_type["concept"].entity_data["term"] == "VWAP"


def test_sample_items_mode_all_filters_excluded_ids(tmp_path):
    db, cid = _seed(tmp_path)
    items = sample_items(
        db,
        content_id=cid,
        entity_types=["trade_example", "concept"],
        mode="all",
        exclude_ids={("trade_example", 1)},
    )
    assert [(i.entity_type, i.entity_id) for i in items] == [("concept", 1)]


def test_sample_items_filters_by_entity_types(tmp_path):
    db, cid = _seed(tmp_path)
    items = sample_items(db, content_id=cid, entity_types=["concept"], mode="all")
    assert all(i.entity_type == "concept" for i in items)
