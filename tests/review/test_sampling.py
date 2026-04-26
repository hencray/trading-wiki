from collections import Counter
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


def test_sample_items_random_returns_n_items(tmp_path):
    db, cid = _seed(tmp_path)
    items = sample_items(
        db,
        content_id=cid,
        entity_types=["trade_example", "concept"],
        mode="random",
        n=1,
        rng_seed=0,
    )
    assert len(items) == 1


def test_sample_items_random_deterministic_with_seed(tmp_path):
    db, cid = _seed(tmp_path)
    a = sample_items(
        db,
        content_id=cid,
        entity_types=["trade_example", "concept"],
        mode="random",
        n=2,
        rng_seed=42,
    )
    b = sample_items(
        db,
        content_id=cid,
        entity_types=["trade_example", "concept"],
        mode="random",
        n=2,
        rng_seed=42,
    )
    assert [(i.entity_type, i.entity_id) for i in a] == [(i.entity_type, i.entity_id) for i in b]


def test_sample_items_random_n_larger_than_pool_returns_all(tmp_path):
    db, cid = _seed(tmp_path)
    items = sample_items(
        db,
        content_id=cid,
        entity_types=["trade_example", "concept"],
        mode="random",
        n=99,
        rng_seed=0,
    )
    assert len(items) == 2


def _seed_stratified(tmp_path: Path) -> tuple[Path, int]:
    """Seed: 4 trade_examples in 'example' chunks, 4 concepts in 'concept' chunks."""
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
            raw_text="x" * 8,
            segments=[
                Segment(
                    seq=i,
                    text=f"chunk {i}",
                    start_seconds=float(i),
                    end_seconds=float(i + 1),
                )
                for i in range(8)
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
                    seq=i,
                    start_seg_seq=i,
                    end_seg_seq=i,
                    label="example" if i < 4 else "concept",
                    confidence="high",
                    summary=f"s{i}",
                )
                for i in range(8)
            ]
        ),
    )
    chunks = load_chunks_for_version(db, content_id=cid, prompt_version="pass1-v1")
    for ch in chunks[:4]:
        save_trade_examples(
            db,
            source_chunk_id=ch["id"],
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
    for ch in chunks[4:]:
        save_concepts(
            db,
            source_chunk_id=ch["id"],
            prompt_version="pass2-concept-v1",
            output=ConceptOutput(
                entities=[
                    Concept(
                        term=f"T{ch['id']}",
                        definition="some standalone definition that is long enough",
                        related_terms=[],
                        confidence="high",
                    )
                ]
            ),
        )
    return db, cid


def test_sample_items_stratified_balances_across_labels(tmp_path):
    db, cid = _seed_stratified(tmp_path)
    items = sample_items(
        db,
        content_id=cid,
        entity_types=["trade_example", "concept"],
        mode="stratified",
        n=4,
        rng_seed=0,
    )
    counts = Counter(i.chunk_label for i in items)
    assert counts == {"example": 2, "concept": 2}


def test_sample_items_stratified_distributes_remainder(tmp_path):
    db, cid = _seed_stratified(tmp_path)
    items = sample_items(
        db,
        content_id=cid,
        entity_types=["trade_example", "concept"],
        mode="stratified",
        n=5,
        rng_seed=0,
    )
    counts = Counter(i.chunk_label for i in items)
    assert sum(counts.values()) == 5
    assert max(counts.values()) - min(counts.values()) <= 1


def test_sample_items_stratified_single_label_returns_n_from_that_bucket(tmp_path):
    db, cid = _seed_stratified(tmp_path)
    items = sample_items(
        db,
        content_id=cid,
        entity_types=["concept"],
        mode="stratified",
        n=3,
        rng_seed=0,
    )
    assert len(items) == 3
    assert {i.chunk_label for i in items} == {"concept"}


def test_sample_items_stratified_n_exceeds_bucket_returns_what_exists(tmp_path):
    db, cid = _seed_stratified(tmp_path)
    items = sample_items(
        db,
        content_id=cid,
        entity_types=["concept"],
        mode="stratified",
        n=99,
        rng_seed=0,
    )
    assert len(items) == 4
