"""Tests for the Pass 3 Concept resolver."""

from __future__ import annotations

import sqlite3
from datetime import UTC
from datetime import datetime as _dt
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


def _seed_concepts(db_path: Path, *, concepts: list[tuple[str, str]]) -> list[int]:
    """Seed concepts at the locked v1 prompt_version. Returns concept_ids."""
    from trading_wiki.config import (
        PROMPT_VERSION_PASS1,
        PROMPT_VERSION_PASS2_CONCEPT,
    )
    from trading_wiki.core.db import apply_migrations, save_content_record
    from trading_wiki.handlers.base import ContentRecord, Segment

    apply_migrations(db_path)
    cid = save_content_record(
        db_path,
        ContentRecord(
            source_type="local_video",
            source_id="vid:p3test",
            title="p3test",
            raw_text="t",
            created_at=_dt(2026, 5, 11, tzinfo=UTC),
            ingested_at=_dt(2026, 5, 11, tzinfo=UTC),
            segments=[Segment(seq=0, text="hi", start_seconds=0.0, end_seconds=1.0)],
        ),
    )
    concept_ids: list[int] = []
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO chunks
            (content_id, seq, start_seg_seq, end_seg_seq, label, confidence,
             summary, text, prompt_version, created_at)
            VALUES (?, 0, 0, 0, 'concept', 'high', 's', 't', ?, '2026-05-11')
            """,
            (cid, PROMPT_VERSION_PASS1),
        )
        chunk_id = conn.execute("SELECT id FROM chunks").fetchone()[0]
        for term, defn in concepts:
            conn.execute(
                """
                INSERT INTO concepts
                (source_chunk_id, term, definition, related_terms,
                 confidence, prompt_version, created_at)
                VALUES (?, ?, ?, '[]', 'high', ?, '2026-05-11')
                """,
                (chunk_id, term, defn, PROMPT_VERSION_PASS2_CONCEPT),
            )
        for r in conn.execute("SELECT id FROM concepts ORDER BY id"):
            concept_ids.append(int(r[0]))
        conn.commit()
    return concept_ids


def _make_unit_vector(seed: int, dim: int = 1536) -> list[float]:
    """Build a deterministic unit-length vector for tests."""
    import random as _random

    rng = _random.Random(seed)
    vals = [rng.gauss(0.0, 1.0) for _ in range(dim)]
    norm = sum(v * v for v in vals) ** 0.5
    return [v / norm for v in vals]


def _fake_openai_client(embeddings: list[list[float]], total_tokens: int = 100) -> SimpleNamespace:
    """Build a fake OpenAI client that returns the given embeddings in order."""

    def create(*, input: list[str], model: str) -> SimpleNamespace:
        # Return one embedding per input string, in order.
        assert len(input) == len(embeddings), (
            f"expected {len(embeddings)} embeddings for {len(input)} inputs"
        )
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=e) for e in embeddings],
            usage=SimpleNamespace(total_tokens=total_tokens),
        )

    return SimpleNamespace(embeddings=SimpleNamespace(create=create))


def test_embed_concepts_writes_one_row_per_unembedded_concept(tmp_path: Path) -> None:
    from trading_wiki.extractors.pass3.concept_resolver import embed_concepts

    db_path = tmp_path / "research.db"
    _seed_concepts(
        db_path,
        concepts=[
            ("supply zone", "An area of selling pressure."),
            ("demand zone", "An area of buying pressure."),
        ],
    )

    vec_a = _make_unit_vector(1)
    vec_b = _make_unit_vector(2)
    openai = _fake_openai_client([vec_a, vec_b], total_tokens=42)

    rows_written, tokens = embed_concepts(db_path, openai_client=openai)
    assert rows_written == 2
    assert tokens == 42

    # Second call should write zero (already embedded).
    rows_written_2, _ = embed_concepts(db_path, openai_client=openai)
    assert rows_written_2 == 0


def test_embed_concepts_raises_on_dim_mismatch(tmp_path: Path) -> None:
    from trading_wiki.extractors.pass3.concept_resolver import embed_concepts

    db_path = tmp_path / "research.db"
    _seed_concepts(db_path, concepts=[("supply", "an area.")])
    # Wrong-dimensional embedding (5 instead of 1536).
    openai = _fake_openai_client([[1.0, 0.0, 0.0, 0.0, 0.0]])
    with pytest.raises(ValueError, match="unexpected embedding dim"):
        embed_concepts(db_path, openai_client=openai)


def test_find_candidate_pairs_returns_above_threshold(tmp_path: Path) -> None:
    """Two near-identical embeddings on different concepts should surface as
    a candidate pair; a third dissimilar embedding should not."""
    from trading_wiki.extractors.pass3.concept_resolver import (
        embed_concepts,
        find_candidate_pairs,
    )

    db_path = tmp_path / "research.db"
    cids = _seed_concepts(
        db_path,
        concepts=[
            ("supply", "an area of selling"),
            ("supply zone", "a place of selling"),
            ("VWAP", "volume-weighted average price"),
        ],
    )

    # First two embeddings nearly identical (cosine ~0.999); third orthogonal.
    near_identical = _make_unit_vector(1)
    perturbed = list(near_identical)
    # Tiny perturbation: bump first 3 dims by a small epsilon, then renormalize.
    eps = 0.01
    for i in range(3):
        perturbed[i] += eps
    norm = sum(v * v for v in perturbed) ** 0.5
    perturbed = [v / norm for v in perturbed]

    orthogonal = _make_unit_vector(2)

    openai = _fake_openai_client([near_identical, perturbed, orthogonal])
    embed_concepts(db_path, openai_client=openai)

    pairs = find_candidate_pairs(db_path, threshold=0.85)
    pair_keys = {(p.concept_a_id, p.concept_b_id) for p in pairs}
    # The first two concepts should match.
    assert (cids[0], cids[1]) in pair_keys
    # The third concept should NOT match either of the first two.
    assert (cids[0], cids[2]) not in pair_keys
    assert (cids[1], cids[2]) not in pair_keys


def test_verify_pair_with_llm_parses_verdict(tmp_path: Path) -> None:
    """verify_pair_with_llm extracts verdict + reason from a tool_use block."""
    from trading_wiki.extractors.pass3.concept_resolver import verify_pair_with_llm

    fake_response = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="tool_use",
                input={"verdict": "same", "reason": "Both describe selling areas."},
            )
        ],
        usage=SimpleNamespace(input_tokens=500, output_tokens=50),
    )

    def create(**kwargs: Any) -> Any:
        return fake_response

    anthropic = SimpleNamespace(messages=SimpleNamespace(create=create))

    verdict, reason, cost = verify_pair_with_llm(
        {"id": 1, "term": "supply", "definition": "an area"},
        {"id": 2, "term": "supply zone", "definition": "a place"},
        anthropic_client=anthropic,
    )
    assert verdict == "same"
    assert "selling" in reason.lower()
    # Cost = 500/1M * $5 + 50/1M * $25 = 0.0025 + 0.00125 = 0.00375
    assert cost == pytest.approx(0.00375)


def test_resolve_concepts_end_to_end_with_mocks(tmp_path: Path) -> None:
    """Full pipeline: 2 near-identical concepts → embed → candidate pair → LLM
    verifies 'same' → concept_resolutions rows persisted with canonical_id = min."""
    from trading_wiki.extractors.pass3.concept_resolver import resolve_concepts

    db_path = tmp_path / "research.db"
    cids = _seed_concepts(
        db_path,
        concepts=[
            ("supply", "an area of selling pressure"),
            ("supply zone", "a place of selling pressure"),
            ("VWAP", "volume-weighted average price"),
        ],
    )

    near = _make_unit_vector(1)
    perturbed = list(near)
    for i in range(3):
        perturbed[i] += 0.01
    norm = sum(v * v for v in perturbed) ** 0.5
    perturbed = [v / norm for v in perturbed]
    orthogonal = _make_unit_vector(2)

    openai = _fake_openai_client([near, perturbed, orthogonal])

    def anthropic_create(**kwargs: Any) -> Any:
        return SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="tool_use",
                    input={"verdict": "same", "reason": "Both describe selling areas."},
                )
            ],
            usage=SimpleNamespace(input_tokens=400, output_tokens=40),
        )

    anthropic = SimpleNamespace(messages=SimpleNamespace(create=anthropic_create))

    result = resolve_concepts(
        db_path, openai_client=openai, anthropic_client=anthropic, threshold=0.85
    )

    assert result.embeddings_written == 3
    # The two near-identical concepts should be the candidate pair.
    pair_keys = {(p.concept_a_id, p.concept_b_id) for p in result.candidate_pairs}
    assert (cids[0], cids[1]) in pair_keys
    # Exactly one verification (one pair).
    assert len(result.verifications) == 1
    assert result.verifications[0]["verdict"] == "same"

    # concept_resolutions rows: 2 (one per concept in the pair), both pointing
    # to canonical = min(cids[0], cids[1]) = cids[0].
    with sqlite3.connect(db_path) as conn:
        rows = list(
            conn.execute(
                "SELECT concept_id, canonical_concept_id, llm_verdict "
                "FROM concept_resolutions ORDER BY concept_id"
            )
        )
    assert len(rows) == 2
    assert rows[0][0] == cids[0]
    assert rows[1][0] == cids[1]
    assert rows[0][1] == rows[1][1] == cids[0]
    assert rows[0][2] == rows[1][2] == "same"


def test_resolve_concepts_different_verdict_keeps_each_as_own_canonical(
    tmp_path: Path,
) -> None:
    """If the LLM verdict is 'different', both concepts keep themselves as canonical."""
    from trading_wiki.extractors.pass3.concept_resolver import resolve_concepts

    db_path = tmp_path / "research.db"
    cids = _seed_concepts(
        db_path,
        concepts=[
            ("supply", "selling"),
            ("VWAP", "price by volume"),
        ],
    )

    # Force a candidate match by giving both concepts near-identical embeddings,
    # even though the LLM will say they're different.
    near = _make_unit_vector(1)
    perturbed = list(near)
    for i in range(3):
        perturbed[i] += 0.01
    norm = sum(v * v for v in perturbed) ** 0.5
    perturbed = [v / norm for v in perturbed]

    openai = _fake_openai_client([near, perturbed])

    def anthropic_create(**kwargs: Any) -> Any:
        return SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="tool_use",
                    input={"verdict": "different", "reason": "Distinct concepts."},
                )
            ],
            usage=SimpleNamespace(input_tokens=400, output_tokens=40),
        )

    anthropic = SimpleNamespace(messages=SimpleNamespace(create=anthropic_create))

    result = resolve_concepts(db_path, openai_client=openai, anthropic_client=anthropic)
    assert len(result.verifications) == 1
    assert result.verifications[0]["verdict"] == "different"

    # Each concept's canonical is itself.
    with sqlite3.connect(db_path) as conn:
        rows = list(
            conn.execute(
                "SELECT concept_id, canonical_concept_id "
                "FROM concept_resolutions ORDER BY concept_id"
            )
        )
    assert rows == [(cids[0], cids[0]), (cids[1], cids[1])]
