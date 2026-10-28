import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import InterfaceError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.pool import NullPool

from kc_house.api import db
from kc_house.api.deps import get_session
from kc_house.api.main import create_app


def test_postgres_connections_are_unpooled_and_fail_fast(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        db, "create_engine", lambda url, **kwargs: captured.update(kwargs, url=url)
    )

    db.make_engine("postgresql+psycopg://u:p@db.internal:5432/houses")

    # No pool: every request opens a connection, so the connect timeout always applies.
    assert captured["poolclass"] is NullPool
    assert captured["connect_args"] == {"connect_timeout": 2}


@pytest.mark.parametrize(
    "error",
    [
        InterfaceError("stmt", {}, Exception("connection lost")),
        PoolTimeoutError("QueuePool limit reached"),
    ],
    ids=["interface-error", "pool-timeout"],
)
def test_every_connection_level_failure_is_a_503_not_a_500(make_settings, error):
    app = create_app(make_settings())

    def broken_session():
        raise error
        yield  # pragma: no cover

    app.dependency_overrides[get_session] = broken_session

    with TestClient(app) as client:
        response = client.get("/api/houses")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database temporarily unavailable."}
