import pytest
from pydantic import ValidationError

from trading_wiki.extractors.pass2.concept import Concept, ConceptOutput


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
