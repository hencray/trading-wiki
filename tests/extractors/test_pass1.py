import pytest
from pydantic import ValidationError

from trading_wiki.extractors.pass1 import (
    CoverageError,
    Pass1Chunk,
    Pass1Output,
    validate_coverage,
)


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


def _good_output() -> Pass1Output:
    return Pass1Output(
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


class TestValidateCoverage:
    def test_passes_for_well_formed_output(self):
        validate_coverage(_good_output(), segment_count=11)

    def test_empty_chunks_rejected(self):
        with pytest.raises(CoverageError, match="empty"):
            validate_coverage(Pass1Output(chunks=[]), segment_count=10)

    def test_first_chunk_must_start_at_zero(self):
        out = Pass1Output(
            chunks=[
                Pass1Chunk(
                    seq=0,
                    start_seg_seq=1,
                    end_seg_seq=10,
                    label="noise",
                    confidence="high",
                    summary="x",
                ),
            ]
        )
        with pytest.raises(CoverageError, match="must start at segment 0"):
            validate_coverage(out, segment_count=11)

    def test_last_chunk_must_cover_final_segment(self):
        out = Pass1Output(
            chunks=[
                Pass1Chunk(
                    seq=0,
                    start_seg_seq=0,
                    end_seg_seq=8,
                    label="noise",
                    confidence="high",
                    summary="x",
                ),
            ]
        )
        with pytest.raises(CoverageError, match="last segment"):
            validate_coverage(out, segment_count=11)

    def test_gap_between_chunks_rejected(self):
        out = Pass1Output(
            chunks=[
                Pass1Chunk(
                    seq=0,
                    start_seg_seq=0,
                    end_seg_seq=2,
                    label="noise",
                    confidence="high",
                    summary="x",
                ),
                Pass1Chunk(
                    seq=1,
                    start_seg_seq=4,
                    end_seg_seq=10,
                    label="strategy",
                    confidence="high",
                    summary="x",
                ),
            ]
        )
        with pytest.raises(CoverageError, match="gap"):
            validate_coverage(out, segment_count=11)

    def test_overlap_between_chunks_rejected(self):
        out = Pass1Output(
            chunks=[
                Pass1Chunk(
                    seq=0,
                    start_seg_seq=0,
                    end_seg_seq=5,
                    label="noise",
                    confidence="high",
                    summary="x",
                ),
                Pass1Chunk(
                    seq=1,
                    start_seg_seq=3,
                    end_seg_seq=10,
                    label="strategy",
                    confidence="high",
                    summary="x",
                ),
            ]
        )
        with pytest.raises(CoverageError, match="overlap"):
            validate_coverage(out, segment_count=11)

    def test_seq_must_be_sequential_zero_indexed(self):
        out = Pass1Output(
            chunks=[
                Pass1Chunk(
                    seq=1,
                    start_seg_seq=0,
                    end_seg_seq=2,
                    label="noise",
                    confidence="high",
                    summary="x",
                ),
                Pass1Chunk(
                    seq=2,
                    start_seg_seq=3,
                    end_seg_seq=10,
                    label="strategy",
                    confidence="high",
                    summary="x",
                ),
            ]
        )
        with pytest.raises(CoverageError, match="seq"):
            validate_coverage(out, segment_count=11)

    def test_start_after_end_rejected(self):
        out = Pass1Output(
            chunks=[
                Pass1Chunk(
                    seq=0,
                    start_seg_seq=5,
                    end_seg_seq=2,
                    label="noise",
                    confidence="high",
                    summary="x",
                ),
            ]
        )
        with pytest.raises(CoverageError, match="start_seg_seq"):
            validate_coverage(out, segment_count=11)


class TestBuildTranscriptText:
    def test_formats_segments_with_seq_and_seconds(self):
        from trading_wiki.extractors.pass1 import build_transcript_text
        from trading_wiki.handlers.base import Segment

        segs = [
            Segment(seq=0, text="Welcome back.", start_seconds=0.0, end_seconds=4.2),
            Segment(seq=1, text="Pivot points.", start_seconds=4.2, end_seconds=10.1),
        ]
        out = build_transcript_text(segs)
        assert "[seg 0] (0.0s-4.2s) Welcome back." in out
        assert "[seg 1] (4.2s-10.1s) Pivot points." in out

    def test_handles_missing_seconds(self):
        from trading_wiki.extractors.pass1 import build_transcript_text
        from trading_wiki.handlers.base import Segment

        segs = [Segment(seq=0, text="No timing.")]
        out = build_transcript_text(segs)
        assert "[seg 0]" in out
        assert "No timing." in out
        assert "s-" not in out


class TestConfig:
    def test_pass1_constants_and_prompt_path(self):
        from trading_wiki.config import (
            MODEL_PASS1,
            PROMPT_PASS1_PATH,
            PROMPT_VERSION_PASS1,
        )

        assert MODEL_PASS1 == "claude-sonnet-4-6"
        assert PROMPT_VERSION_PASS1 == "pass1-v1"
        assert PROMPT_PASS1_PATH.is_file()
        text = PROMPT_PASS1_PATH.read_text(encoding="utf-8")
        assert len(text) > 100
        for label in [
            "strategy",
            "concept",
            "example",
            "psychology",
            "market_commentary",
            "qa",
            "noise",
        ]:
            assert label in text, f"prompt missing label: {label}"
