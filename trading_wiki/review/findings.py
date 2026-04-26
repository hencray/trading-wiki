"""Read/write the per-content_id markdown findings file used by the review UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

EntityType = Literal["trade_example", "concept"]
Status = Literal["accept", "needs_fix", "skip"]

REVIEWS_DIR = Path("docs/superpowers/reviews")


@dataclass(frozen=True)
class Finding:
    entity_type: EntityType
    entity_id: int
    status: Status
    chunk_id: int
    chunk_label: str
    prompt_version: str
    reviewed_at: datetime
    notes: str


def findings_path_for(content_id: int, base_dir: Path | str = REVIEWS_DIR) -> Path:
    """Return the markdown findings path for ``content_id`` under ``base_dir``."""
    return Path(base_dir) / f"content{content_id}.md"
