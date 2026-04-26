import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from trading_wiki.core.db import (
    apply_migrations,
    load_concepts_for_version,
    save_chunks,
    save_content_record,
)
from trading_wiki.core.llm import UsageRecord
from trading_wiki.extractors.pass1 import Pass1Chunk, Pass1Output
from trading_wiki.extractors.pass2.concept import (
    Concept,
    ConceptOutput,
    extract_concepts_for_chunk,
)
from trading_wiki.handlers.base import ContentRecord, Segment


class TestConcept:
    def test_minimal_required_fields_parse(self):
        c = Concept(
            term="pivot point",
            definition="Average of prior period's high, low, and close.",
            confidence="high",
        )
        assert c.term == "pivot point"
        assert c.related_terms == []

    def test_with_related_terms_parses(self):
        c = Concept(
            term="pivot point",
            definition="Average of prior period's high, low, and close.",
            related_terms=["resistance", "support", "pullback hold"],
            confidence="medium",
        )
        assert len(c.related_terms) == 3

    def test_term_over_80_chars_rejected(self):
        with pytest.raises(ValidationError):
            Concept(term="x" * 81, definition="a definition", confidence="high")

    def test_definition_under_10_chars_rejected(self):
        # Prevents one-word "definitions" that are useless.
        with pytest.raises(ValidationError):
            Concept(term="pivot", definition="short", confidence="high")

    def test_definition_over_400_chars_rejected(self):
        with pytest.raises(ValidationError):
            Concept(
                term="pivot",
                definition="x" * 401,
                confidence="high",
            )

    def test_related_terms_over_15_rejected(self):
        with pytest.raises(ValidationError):
            Concept(
                term="pivot",
                definition="A pivot is a level.",
                related_terms=[f"t{i}" for i in range(16)],
                confidence="high",
            )

    def test_unknown_confidence_rejected(self):
        with pytest.raises(ValidationError):
            Concept(
                term="pivot",
                definition="A pivot is a level.",
                confidence="mid",
            )

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            Concept.model_validate(
                {
                    "term": "pivot",
                    "definition": "A pivot is a level.",
                    "confidence": "high",
                    "bogus": "nope",
                }
            )


class TestConceptOutput:
    def test_empty_entities_list_is_valid(self):
        out = ConceptOutput(entities=[])
        assert out.entities == []

    def test_multi_entity_output_parses(self):
        out = ConceptOutput(
            entities=[
                Concept(term="pivot", definition="A pivot is a level.", confidence="high"),
                Concept(
                    term="pullback hold",
                    definition="Setup where price reclaims pivot in the first hour.",
                    confidence="medium",
                ),
            ]
        )
        assert len(out.entities) == 2


# ───────────────────────── extractor tests (LLM mocked) ─────────────────────────


def _seed_chunk(db_path: Path, label: str = "concept") -> int:
    record = ContentRecord(
        source_type="test",
        source_id=f"vid-{label}",
        title="t",
        created_at=datetime(2026, 4, 25),
        ingested_at=datetime(2026, 4, 25),
        raw_text="r",
        segments=[
            Segment(seq=0, text="A pivot is a level.", start_seconds=0.0, end_seconds=1.0),
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
                    seq=0,
                    start_seg_seq=0,
                    end_seg_seq=0,
                    label=label,
                    confidence="high",
                    summary="x",
                ),
            ]
        ),
    )
    with sqlite3.connect(db_path) as conn:
        chunk_id: int = conn.execute("SELECT id FROM chunks").fetchone()[0]
        return chunk_id


def _stub_usage(
    input_tokens: int = 80,
    output_tokens: int = 40,
    cost: float = 0.001,
) -> UsageRecord:
    return UsageRecord(
        model="claude-sonnet-4-6",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_estimate_usd=cost,
    )


class TestExtractConceptsForChunk:
    @patch("trading_wiki.extractors.pass2.concept.call_structured")
    def test_happy_path_writes_rows(self, mock_call, tmp_path):
        db_path = tmp_path / "research.db"
        apply_migrations(db_path)
        chunk_id = _seed_chunk(db_path)

        out = ConceptOutput(
            entities=[
                Concept(
                    term="pivot point",
                    definition="Average of prior period's high, low, and close.",
                    related_terms=["resistance"],
                    confidence="high",
                ),
            ]
        )
        mock_call.return_value = (out, _stub_usage(), [])

        entities, usage = extract_concepts_for_chunk(
            chunk_id=chunk_id,
            db_path=db_path,
        )
        assert len(entities) == 1
        assert entities[0].term == "pivot point"
        assert usage.input_tokens == 80

        rows = load_concepts_for_version(
            db_path,
            source_chunk_id=chunk_id,
            prompt_version="pass2-concept-v1",
        )
        assert len(rows) == 1
        assert rows[0]["related_terms"] == ["resistance"]

    @patch("trading_wiki.extractors.pass2.concept.call_structured")
    def test_empty_entities_writes_no_rows(self, mock_call, tmp_path):
        db_path = tmp_path / "research.db"
        apply_migrations(db_path)
        chunk_id = _seed_chunk(db_path)

        mock_call.return_value = (ConceptOutput(entities=[]), _stub_usage(), [])

        entities, _ = extract_concepts_for_chunk(chunk_id=chunk_id, db_path=db_path)
        assert entities == []
        assert (
            load_concepts_for_version(
                db_path,
                source_chunk_id=chunk_id,
                prompt_version="pass2-concept-v1",
            )
            == []
        )

    @patch("trading_wiki.extractors.pass2.concept.call_structured")
    def test_idempotent_skips_when_rows_exist(self, mock_call, tmp_path):
        db_path = tmp_path / "research.db"
        apply_migrations(db_path)
        chunk_id = _seed_chunk(db_path)

        out = ConceptOutput(
            entities=[
                Concept(
                    term="pivot",
                    definition="A pivot is a level.",
                    related_terms=["resistance", "support"],
                    confidence="high",
                ),
            ]
        )
        mock_call.return_value = (out, _stub_usage(), [])
        extract_concepts_for_chunk(chunk_id=chunk_id, db_path=db_path)
        assert mock_call.call_count == 1

        entities, usage = extract_concepts_for_chunk(
            chunk_id=chunk_id,
            db_path=db_path,
        )
        assert mock_call.call_count == 1
        assert len(entities) == 1
        # Idempotency-rebuild round-trips related_terms back into a Python list.
        assert entities[0].related_terms == ["resistance", "support"]
        assert usage.cost_estimate_usd == 0.0

    @patch("trading_wiki.extractors.pass2.concept.call_structured")
    def test_unknown_chunk_id_raises(self, mock_call, tmp_path):
        db_path = tmp_path / "research.db"
        apply_migrations(db_path)
        with pytest.raises(LookupError, match="chunk_id"):
            extract_concepts_for_chunk(chunk_id=999, db_path=db_path)
        mock_call.assert_not_called()

    @patch("trading_wiki.extractors.pass2.concept.call_structured")
    def test_passes_chunk_text_as_user_message(self, mock_call, tmp_path):
        db_path = tmp_path / "research.db"
        apply_migrations(db_path)
        chunk_id = _seed_chunk(db_path)

        mock_call.return_value = (ConceptOutput(entities=[]), _stub_usage(), [])
        extract_concepts_for_chunk(chunk_id=chunk_id, db_path=db_path)

        kwargs = mock_call.call_args.kwargs
        assert kwargs["model"] == "claude-sonnet-4-6"
        assert "Concept" in kwargs["system"]
        assert kwargs["messages"] == [{"role": "user", "content": "A pivot is a level."}]
        assert kwargs["schema"] is ConceptOutput
