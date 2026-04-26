from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from trading_wiki.handlers.base import BaseHandler, ContentRecord, Segment


def test_content_record_accepts_required_fields():
    record = ContentRecord(
        source_type="local_video",
        source_id="abc123",
        title="sample lesson 1",
        created_at=datetime(2026, 4, 1, 12, 0, 0),
        ingested_at=datetime(2026, 4, 22, 18, 0, 0),
        raw_text="Hello world.",
    )
    assert record.source_type == "local_video"
    assert record.source_id == "abc123"
    assert record.title == "sample lesson 1"
    assert record.raw_text == "Hello world."


def test_segment_accepts_required_fields():
    segment = Segment(seq=0, text="hello")
    assert segment.seq == 0
    assert segment.text == "hello"


def test_segment_accepts_optional_timestamps():
    segment = Segment(seq=0, text="hello", start_seconds=12.5, end_seconds=25.0)
    assert segment.start_seconds == 12.5
    assert segment.end_seconds == 25.0


def test_segment_timestamps_default_to_none():
    segment = Segment(seq=0, text="hello")
    assert segment.start_seconds is None
    assert segment.end_seconds is None


def test_segment_rejects_unknown_fields():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Segment(seq=0, text="hello", typo_field=42)  # type: ignore[call-arg]


def test_content_record_rejects_unknown_fields():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ContentRecord(
            source_type="x",
            source_id="y",
            title="z",
            created_at=datetime(2026, 1, 1),
            ingested_at=datetime(2026, 1, 1),
            raw_text="hi",
            typo_field=42,  # type: ignore[call-arg]
        )


def _minimal_record_kwargs() -> dict[str, Any]:
    return {
        "source_type": "x",
        "source_id": "y",
        "title": "z",
        "created_at": datetime(2026, 1, 1),
        "ingested_at": datetime(2026, 1, 1),
        "raw_text": "hi",
    }


def test_content_record_accepts_segments():
    record = ContentRecord(
        **_minimal_record_kwargs(),
        segments=[Segment(seq=0, text="part 1"), Segment(seq=1, text="part 2")],
    )
    assert len(record.segments) == 2
    assert record.segments[0].text == "part 1"


def test_content_record_segments_default_to_empty():
    record = ContentRecord(**_minimal_record_kwargs())
    assert record.segments == []


def test_content_record_optional_fields_default_to_none_or_empty():
    record = ContentRecord(**_minimal_record_kwargs())
    assert record.author is None
    assert record.parent_id is None
    assert record.metadata == {}


def test_content_record_accepts_optional_fields():
    record = ContentRecord(
        **_minimal_record_kwargs(),
        author="Test Author",
        parent_id="course-module-3",
        metadata={"duration_seconds": 1234, "channel": "test-channel"},
    )
    assert record.author == "Test Author"
    assert record.parent_id == "course-module-3"
    assert record.metadata == {"duration_seconds": 1234, "channel": "test-channel"}


def test_base_handler_cannot_be_instantiated_directly():
    with pytest.raises(TypeError, match="abstract"):
        BaseHandler()  # type: ignore[abstract]


def test_base_handler_subclass_missing_methods_cannot_be_instantiated():
    class IncompleteHandler(BaseHandler):
        pass

    with pytest.raises(TypeError, match="abstract"):
        IncompleteHandler()  # type: ignore[abstract]


def test_base_handler_concrete_subclass_dispatches():
    class FakeHandler(BaseHandler):
        def can_handle(self, source: str) -> bool:
            return source.startswith("fake:")

        def ingest(self, source: str) -> ContentRecord:
            return ContentRecord(
                source_type="fake",
                source_id=source,
                title="fake title",
                created_at=datetime(2026, 1, 1),
                ingested_at=datetime(2026, 1, 1),
                raw_text="hi",
            )

    handler = FakeHandler()
    assert handler.can_handle("fake:abc") is True
    assert handler.can_handle("real:xyz") is False
    record = handler.ingest("fake:abc")
    assert record.source_type == "fake"
    assert record.source_id == "fake:abc"
