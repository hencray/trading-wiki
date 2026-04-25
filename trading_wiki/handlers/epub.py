from pathlib import Path

from trading_wiki.handlers.base import BaseHandler, ContentRecord


class EpubHandler(BaseHandler):
    """Stub. Implementation deferred — will use ebooklib."""

    def can_handle(self, source: str) -> bool:
        return Path(source).suffix.lower() == ".epub"

    def ingest(self, source: str) -> ContentRecord:
        raise NotImplementedError("EPUB ingestion deferred to post-Phase-1")
