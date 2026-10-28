"""Runtime configuration, read from ``KC_*`` environment variables or ``.env``."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KC_", env_file=".env", extra="ignore")

    # SQLite keeps local runs and tests dependency-free; deployments use Postgres.
    database_url: str = "sqlite:///./houses.db"
    model_dir: Path = Path("artifacts")
    create_tables: bool = True

    # Writes (POST/PUT/DELETE) are refused unless a key is configured, or
    # ``open_writes`` is set explicitly for local experiments.
    api_key: SecretStr | None = None
    open_writes: bool = False

    github_url: str = "https://github.com/shadmanArko/mle-refactoring-project"
    log_level: str = "INFO"
