from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Typed accessor for environment variables and `.env` values.

    All API keys are optional and default to ``None``; calling code that
    needs one validates at the use site rather than at startup so the
    project remains runnable without keys for systems not yet built.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    polygon_api_key: SecretStr | None = None
    alpaca_api_key_id: SecretStr | None = None
    alpaca_api_secret_key: SecretStr | None = None
    alpaca_base_url: str = "https://paper-api.alpaca.markets"

    log_level: LogLevel = "INFO"
    db_path: Path = Path("./data/research.db")
    content_dir: Path = Path("./content")
