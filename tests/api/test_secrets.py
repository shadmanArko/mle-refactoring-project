import json

import pytest
from sqlalchemy.engine import make_url

from kc_house.api.secrets import SecretError, resolve_secrets
from kc_house.api.settings import Settings

KEY_ARN = "arn:aws:secretsmanager:eu-central-1:123456789012:secret:key-AbCdEf"
DB_ARN = "arn:aws:secretsmanager:eu-central-1:123456789012:secret:db-AbCdEf"


class FakeSecretsManager:
    def __init__(self, secrets: dict[str, str]) -> None:
        self.secrets = secrets
        self.requested: list[str] = []

    def get_secret_value(self, SecretId: str) -> dict:
        self.requested.append(SecretId)
        if SecretId not in self.secrets:
            raise LookupError("ResourceNotFoundException")
        return {"SecretString": self.secrets[SecretId]}


def settings(**values) -> Settings:
    return Settings(_env_file=None, **values)  # pyright: ignore[reportCallIssue]


def test_nothing_is_fetched_when_no_secret_is_configured():
    client = FakeSecretsManager({})
    original = settings(api_key="local")

    assert resolve_secrets(original, client) is original
    assert client.requested == []


def test_the_api_key_comes_from_the_secret():
    client = FakeSecretsManager({KEY_ARN: "s3cr3t-from-aws"})

    resolved = resolve_secrets(settings(api_key_secret_arn=KEY_ARN), client)

    assert resolved.api_key is not None
    assert resolved.api_key.get_secret_value() == "s3cr3t-from-aws"


def test_an_explicit_api_key_is_never_overridden():
    client = FakeSecretsManager({KEY_ARN: "from-aws"})

    resolved = resolve_secrets(
        settings(api_key="explicit", api_key_secret_arn=KEY_ARN), client
    )

    assert resolved.api_key is not None
    assert resolved.api_key.get_secret_value() == "explicit"
    assert client.requested == []


def test_the_database_url_is_built_with_tls_and_an_escaped_password():
    password = "p@ss:w/rd#?%&"
    client = FakeSecretsManager(
        {DB_ARN: json.dumps({"username": "kc", "password": password})}
    )

    resolved = resolve_secrets(
        settings(
            database_secret_arn=DB_ARN,
            database_host="db.example.internal",
            database_name="houses",
        ),
        client,
    )

    url = make_url(resolved.database_url)
    assert (url.drivername, url.host, url.port) == (
        "postgresql+psycopg",
        "db.example.internal",
        5432,
    )
    assert url.password == password  # survived escaping and parsing
    assert url.query == {"sslmode": "require"}


def test_a_secret_that_cannot_be_read_stops_start_up():
    with pytest.raises(SecretError, match=KEY_ARN):
        resolve_secrets(settings(api_key_secret_arn=KEY_ARN), FakeSecretsManager({}))


def test_a_database_secret_without_a_host_cannot_silently_fall_back_to_sqlite():
    with pytest.raises(SecretError, match="KC_DATABASE_HOST"):
        resolve_secrets(settings(database_secret_arn=DB_ARN), FakeSecretsManager({}))


def test_a_database_secret_without_a_password_stops_start_up():
    client = FakeSecretsManager({DB_ARN: json.dumps({"username": "kc"})})

    with pytest.raises(SecretError, match="username and password"):
        resolve_secrets(
            settings(database_secret_arn=DB_ARN, database_host="db"), client
        )


def test_the_app_reads_its_secrets_when_it_starts(make_settings, monkeypatch, house):
    from fastapi.testclient import TestClient

    from kc_house.api import main

    fake = FakeSecretsManager({KEY_ARN: "key-from-aws"})
    monkeypatch.setattr(main, "resolve_secrets", lambda s: resolve_secrets(s, fake))
    config = make_settings(api_key=None, api_key_secret_arn=KEY_ARN)

    with TestClient(main.create_app(config)) as client:
        denied = client.post("/api/houses", json=house)
        allowed = client.post(
            "/api/houses", json=house, headers={"X-API-Key": "key-from-aws"}
        )

    assert denied.status_code == 401
    assert allowed.status_code == 201
