"""Read secrets from AWS Secrets Manager at start-up, so none sit in the environment."""

import json
import logging
from typing import Any

from pydantic import SecretStr
from sqlalchemy.engine import URL

from kc_house.api.settings import Settings

logger = logging.getLogger(__name__)


class SecretError(RuntimeError):
    """A configured secret could not be read or understood."""


def _default_client() -> Any:
    import boto3  # imported here so local runs never need AWS libraries or config

    return boto3.client("secretsmanager")


def _read(client: Any, arn: str) -> str:
    try:
        return client.get_secret_value(SecretId=arn)["SecretString"]
    except Exception as error:  # boto raises many types; the cause is in the chain
        raise SecretError(f"Could not read secret {arn}") from error


def resolve_secrets(settings: Settings, client: Any = None) -> Settings:
    """Return settings with the API key and database URL filled in from secrets.

    Does nothing when no secret ARN is configured (local runs, Docker Compose).
    Raises ``SecretError`` if a configured secret cannot be read: a deployment with a
    broken secret should fail loudly, not run quietly without writes or a database.
    """
    if settings.database_secret_arn and not settings.database_host:
        raise SecretError(
            "KC_DATABASE_SECRET_ARN is set but KC_DATABASE_HOST is not; refusing to "
            "fall back to the local SQLite file"
        )
    wants_key = settings.api_key_secret_arn and settings.api_key is None
    wants_db = settings.database_secret_arn and settings.database_host
    if not (wants_key or wants_db):
        return settings

    client = client or _default_client()
    updates: dict[str, Any] = {}

    if wants_key:
        updates["api_key"] = SecretStr(_read(client, settings.api_key_secret_arn or ""))
        logger.info("api key loaded from secrets manager")

    if wants_db:
        raw = _read(client, settings.database_secret_arn or "")
        try:
            credentials = json.loads(raw)
            url = URL.create(
                "postgresql+psycopg",
                username=credentials["username"],
                password=credentials["password"],
                host=settings.database_host,
                port=settings.database_port,
                database=settings.database_name,
                query={"sslmode": "require"},
            )
        except (ValueError, KeyError) as error:
            raise SecretError(
                "Database secret must hold username and password"
            ) from error
        # render_as_string escapes special characters in the password.
        updates["database_url"] = url.render_as_string(hide_password=False)
        logger.info("database credentials loaded from secrets manager")

    return settings.model_copy(update=updates)
