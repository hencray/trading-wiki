from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from trading_wiki.core.secrets import Settings

_ENV_KEYS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "POLYGON_API_KEY",
    "ALPACA_API_KEY_ID",
    "ALPACA_API_SECRET_KEY",
    "ALPACA_BASE_URL",
    "LOG_LEVEL",
    "DB_PATH",
    "CONTENT_DIR",
)


@pytest.fixture
def clean_env(monkeypatch):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_settings_defaults(clean_env):
    settings = Settings(_env_file=None)
    assert settings.log_level == "INFO"
    assert settings.alpaca_base_url == "https://paper-api.alpaca.markets"
    assert settings.db_path == Path("./data/research.db")
    assert settings.content_dir == Path("./content")
    assert settings.openai_api_key is None
    assert settings.anthropic_api_key is None
    assert settings.polygon_api_key is None
    assert settings.alpaca_api_key_id is None
    assert settings.alpaca_api_secret_key is None


def test_settings_reads_env_vars(clean_env, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-1234")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DB_PATH", "/tmp/test.db")
    settings = Settings(_env_file=None)
    assert isinstance(settings.openai_api_key, SecretStr)
    assert settings.openai_api_key.get_secret_value() == "sk-test-1234"
    assert settings.log_level == "DEBUG"
    assert settings.db_path == Path("/tmp/test.db")


def test_settings_secrets_are_redacted_in_repr(clean_env, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-1234")
    settings = Settings(_env_file=None)
    rendered = repr(settings)
    assert "sk-test-1234" not in rendered


def test_settings_rejects_invalid_log_level(clean_env, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "BANANA")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_loads_env_file(clean_env, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=from-file\nLOG_LEVEL=WARNING\n")
    settings = Settings(_env_file=env_file)
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "from-file"
    assert settings.log_level == "WARNING"
