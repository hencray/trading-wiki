from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Segment(StrictModel):
    seq: int
    text: str
    start_seconds: float | None = None
    end_seconds: float | None = None


class ContentRecord(StrictModel):
    source_type: str
    source_id: str
    title: str
    created_at: datetime
    ingested_at: datetime
    raw_text: str
    author: str | None = None
    parent_id: str | None = None
    segments: list[Segment] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseHandler(ABC):
    @abstractmethod
    def can_handle(self, source: str) -> bool: ...

    @abstractmethod
    def ingest(self, source: str) -> ContentRecord: ...
