import pytest
from pydantic import ValidationError

from trading_wiki.extractors.pass1 import Pass1Chunk, Pass1Output


class TestPass1Chunk:
    def test_valid_chunk_parses(self):
        chunk = Pass1Chunk(
            seq=0,
            start_seg_seq=0,
            end_seg_seq=4,
            label="strategy",
            confidence="high",
            summary="Pivot point entry rules.",
        )
        assert chunk.seq == 0
        assert chunk.label == "strategy"

    def test_unknown_label_rejected(self):
        with pytest.raises(ValidationError):
            Pass1Chunk(
                seq=0,
                start_seg_seq=0,
                end_seg_seq=0,
                label="banter",
                confidence="high",
                summary="x",
            )

    def test_unknown_confidence_rejected(self):
        with pytest.raises(ValidationError):
            Pass1Chunk(
                seq=0,
                start_seg_seq=0,
                end_seg_seq=0,
                label="noise",
                confidence="maybe",
                summary="x",
            )

    def test_summary_over_120_chars_rejected(self):
        with pytest.raises(ValidationError):
            Pass1Chunk(
                seq=0,
                start_seg_seq=0,
                end_seg_seq=0,
                label="noise",
                confidence="high",
                summary="x" * 121,
            )

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            Pass1Chunk.model_validate(
                {
                    "seq": 0,
                    "start_seg_seq": 0,
                    "end_seg_seq": 0,
                    "label": "noise",
                    "confidence": "high",
                    "summary": "x",
                    "extra_field": "nope",
                }
            )


class TestPass1Output:
    def test_empty_chunks_list_is_valid_pydantically(self):
        Pass1Output(chunks=[])

    def test_typical_output_parses(self):
        out = Pass1Output(
            chunks=[
                Pass1Chunk(
                    seq=0,
                    start_seg_seq=0,
                    end_seg_seq=2,
                    label="noise",
                    confidence="high",
                    summary="intro",
                ),
                Pass1Chunk(
                    seq=1,
                    start_seg_seq=3,
                    end_seg_seq=10,
                    label="strategy",
                    confidence="medium",
                    summary="entry rules",
                ),
            ]
        )
        assert len(out.chunks) == 2
