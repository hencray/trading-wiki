from trading_wiki.handlers.base import BaseHandler, ContentRecord


class ArticleHandler(BaseHandler):
    """Stub. Implementation deferred — will use trafilatura."""

    def can_handle(self, source: str) -> bool:
        lower = source.lower()
        return lower.startswith("http://") or lower.startswith("https://")

    def ingest(self, source: str) -> ContentRecord:
        raise NotImplementedError("Article ingestion deferred to post-Phase-1")
