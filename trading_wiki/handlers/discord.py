from pathlib import Path

from trading_wiki.core.pasted_text import ingest_pasted_text
from trading_wiki.handlers.base import BaseHandler, ContentRecord

_PREFIX = "discord:"


class DiscordHandler(BaseHandler):
    """Ingest a Discord channel/thread pasted into a local text file.

    Source format: ``discord:<path>``. The file is stored verbatim
    content-addressed; message-level parsing (authors, timestamps, replies)
    is deferred to Phase 2 LLM extraction.
    """

    def __init__(self, storage_dir: Path) -> None:
        self._storage_dir = storage_dir

    def can_handle(self, source: str) -> bool:
        return source.startswith(_PREFIX)

    def ingest(self, source: str) -> ContentRecord:
        if not self.can_handle(source):
            raise ValueError(f"cannot handle {source!r}")
        path = Path(source[len(_PREFIX) :])
        return ingest_pasted_text(path, "discord", self._storage_dir)
