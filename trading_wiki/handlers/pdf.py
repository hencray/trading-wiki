from pathlib import Path

from trading_wiki.handlers.base import BaseHandler, ContentRecord


class PdfHandler(BaseHandler):
    """Stub. Implementation deferred — will use pdfplumber/PyMuPDF + OCR fallback."""

    def can_handle(self, source: str) -> bool:
        return Path(source).suffix.lower() == ".pdf"

    def ingest(self, source: str) -> ContentRecord:
        raise NotImplementedError("PDF ingestion deferred to post-Phase-1")
