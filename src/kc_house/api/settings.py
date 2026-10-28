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

    # On AWS the secrets are never in the environment: the app is given the ARN of
    # each secret and reads the value from Secrets Manager at start-up (secrets.py).
    api_key_secret_arn: str | None = None
    database_secret_arn: str | None = None
    database_host: str | None = None
    database_port: int = 5432
    database_name: str = "houses"

    github_url: str = "https://github.com/shadmanArko/mle-refactoring-project"
    log_level: str = "INFO"
