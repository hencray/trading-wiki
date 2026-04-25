import pytest

from trading_wiki.handlers.article import ArticleHandler
from trading_wiki.handlers.base import BaseHandler
from trading_wiki.handlers.epub import EpubHandler
from trading_wiki.handlers.pdf import PdfHandler


def test_pdf_handler_subclass_of_base():
    assert issubclass(PdfHandler, BaseHandler)


def test_pdf_handler_matches_pdf_extension():
    handler = PdfHandler()
    assert handler.can_handle("/p/lesson.pdf") is True
    assert handler.can_handle("/p/lesson.PDF") is True
    assert handler.can_handle("/p/lesson.epub") is False
    assert handler.can_handle("/p/lesson.txt") is False
    assert handler.can_handle("https://example.com/article") is False


def test_pdf_handler_ingest_raises_not_implemented():
    handler = PdfHandler()
    with pytest.raises(NotImplementedError, match="deferred"):
        handler.ingest("/p/lesson.pdf")


def test_epub_handler_subclass_of_base():
    assert issubclass(EpubHandler, BaseHandler)


def test_epub_handler_matches_epub_extension():
    handler = EpubHandler()
    assert handler.can_handle("/p/book.epub") is True
    assert handler.can_handle("/p/book.EPUB") is True
    assert handler.can_handle("/p/book.pdf") is False
    assert handler.can_handle("/p/book.txt") is False


def test_epub_handler_ingest_raises_not_implemented():
    handler = EpubHandler()
    with pytest.raises(NotImplementedError, match="deferred"):
        handler.ingest("/p/book.epub")


def test_article_handler_subclass_of_base():
    assert issubclass(ArticleHandler, BaseHandler)


def test_article_handler_matches_http_urls():
    handler = ArticleHandler()
    assert handler.can_handle("https://example.com/post") is True
    assert handler.can_handle("http://example.com/post") is True
    assert handler.can_handle("HTTPS://EXAMPLE.COM/post") is True
    assert handler.can_handle("/local/file.txt") is False
    assert handler.can_handle("discord:/path/paste.txt") is False
    assert handler.can_handle("ftp://example.com/file") is False


def test_article_handler_ingest_raises_not_implemented():
    handler = ArticleHandler()
    with pytest.raises(NotImplementedError, match="deferred"):
        handler.ingest("https://example.com/post")
