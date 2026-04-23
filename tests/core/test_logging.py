import json

import pytest
import structlog

from trading_wiki.core.logging import configure_logging


@pytest.fixture(autouse=True)
def _reset_structlog():
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()


def test_configure_logging_emits_json(capsys):
    configure_logging()
    logger = structlog.get_logger()
    logger.info("test_event", foo="bar", number=42)
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["event"] == "test_event"
    assert parsed["foo"] == "bar"
    assert parsed["number"] == 42
    assert parsed["level"] == "info"


def test_configure_logging_includes_iso_timestamp(capsys):
    configure_logging()
    logger = structlog.get_logger()
    logger.info("ts_event")
    parsed = json.loads(capsys.readouterr().out)
    assert "timestamp" in parsed
    assert parsed["timestamp"].endswith("Z") or "T" in parsed["timestamp"]


def test_configure_logging_respects_level(capsys):
    configure_logging(level="WARNING")
    logger = structlog.get_logger()
    logger.info("should_not_appear")
    logger.warning("should_appear")
    out = capsys.readouterr().out
    assert "should_not_appear" not in out
    assert "should_appear" in out


def test_configure_logging_is_idempotent(capsys):
    configure_logging()
    configure_logging()
    logger = structlog.get_logger()
    logger.info("post_double_config")
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["event"] == "post_double_config"
