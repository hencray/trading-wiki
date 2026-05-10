"""Tests for the contamination-ablation sampler."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from trading_wiki.config import PROMPT_VERSION_PASS1
from trading_wiki.core.db import apply_migrations, save_content_record
from trading_wiki.extractors.pass2.ablation import sample_chunks_for_ablation
from trading_wiki.handlers.base import ContentRecord, Segment


def _seed_chunks_across_labels(db_path: Path) -> None:
    """Seed 30 chunks, 5 per Pass 1 label, all at PROMPT_VERSION_PASS1."""
    apply_migrations(db_path)
    cid = save_content_record(
        db_path,
        ContentRecord(
            source_type="local_video",
            source_id="vid:seed",
            title="seed",
            raw_text="t",
            created_at=datetime(2026, 5, 10, tzinfo=UTC),
            ingested_at=datetime(2026, 5, 10, tzinfo=UTC),
            segments=[Segment(seq=0, text="hi", start_seconds=0.0, end_seconds=1.0)],
        ),
    )
    labels = ["example", "concept", "qa", "strategy", "psychology", "market_commentary"]
    seq = 0
    with sqlite3.connect(db_path) as conn:
        for label in labels:
            for _ in range(5):
                conn.execute(
                    """
                    INSERT INTO chunks
                    (content_id, seq, start_seg_seq, end_seg_seq, label, confidence,
                     summary, text, prompt_version, created_at)
                    VALUES (?, ?, 0, 0, ?, 'high', 's', 't', ?, '2026-05-10')
                    """,
                    (cid, seq, label, PROMPT_VERSION_PASS1),
                )
                seq += 1
        conn.commit()


def test_sampler_pulls_correct_strata(tmp_path: Path) -> None:
    db_path = tmp_path / "research.db"
    _seed_chunks_across_labels(db_path)

    samples = sample_chunks_for_ablation(
        db_path=db_path,
        n_priming_te=3,
        n_priming_concept=4,
        n_routing=2,
        seed=42,
    )

    assert len(samples.te_priming) == 3
    assert {r["label"] for r in samples.te_priming} == {"example"}

    assert len(samples.concept_priming) == 4
    assert {r["label"] for r in samples.concept_priming} <= {"concept", "qa"}

    assert len(samples.routing) == 2
    assert {r["label"] for r in samples.routing} <= {
        "strategy",
        "psychology",
        "market_commentary",
        "noise",
    }


def test_sampler_is_deterministic_with_seed(tmp_path: Path) -> None:
    db_path = tmp_path / "research.db"
    _seed_chunks_across_labels(db_path)

    s1 = sample_chunks_for_ablation(
        db_path=db_path,
        n_priming_te=3,
        n_priming_concept=3,
        n_routing=3,
        seed=42,
    )
    s2 = sample_chunks_for_ablation(
        db_path=db_path,
        n_priming_te=3,
        n_priming_concept=3,
        n_routing=3,
        seed=42,
    )

    assert [r["id"] for r in s1.te_priming] == [r["id"] for r in s2.te_priming]
    assert [r["id"] for r in s1.concept_priming] == [r["id"] for r in s2.concept_priming]
    assert [r["id"] for r in s1.routing] == [r["id"] for r in s2.routing]


def test_sampler_returns_all_when_stratum_understocked(tmp_path: Path) -> None:
    db_path = tmp_path / "research.db"
    _seed_chunks_across_labels(db_path)

    samples = sample_chunks_for_ablation(
        db_path=db_path,
        n_priming_te=99,  # only 5 example chunks exist
        n_priming_concept=2,
        n_routing=2,
        seed=42,
    )

    assert len(samples.te_priming) == 5  # capped at available
