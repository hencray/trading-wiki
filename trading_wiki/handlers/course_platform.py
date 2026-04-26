from pathlib import Path

from trading_wiki.core.pasted_text import ingest_pasted_text
from trading_wiki.handlers.base import BaseHandler, ContentRecord

_PREFIX = "course:"


class CoursePlatformHandler(BaseHandler):
    """Ingest course-platform text the user has extracted to a local file.

    Source format: ``course:<path>``. The user provides lesson text as a local
    file (no platform-specific scraper) and the handler stores it verbatim.
    Same shape as ``DiscordHandler`` — different ``source_type`` keeps the
    credibility tier and provenance distinct downstream.
    """

    def __init__(self, storage_dir: Path) -> None:
        self._storage_dir = storage_dir

    def can_handle(self, source: str) -> bool:
        return source.startswith(_PREFIX)

    def ingest(self, source: str) -> ContentRecord:
        if not self.can_handle(source):
            raise ValueError(f"cannot handle {source!r}")
        path = Path(source[len(_PREFIX) :])
        return ingest_pasted_text(path, "course_platform", self._storage_dir)
