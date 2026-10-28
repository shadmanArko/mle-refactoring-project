"""The same API against a real Postgres.

Skipped unless KC_TEST_DATABASE_URL points at a disposable Postgres, for example:
    KC_TEST_DATABASE_URL=postgresql+psycopg://test:test@localhost:5432/houses_test
CI provides one. These guard the one code path SQLite cannot exercise.
"""

import os
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from kc_house.api.main import create_app

URL = os.environ.get("KC_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not URL, reason="KC_TEST_DATABASE_URL is not set")


def reset(app: FastAPI) -> None:
    with app.state.engine.begin() as connection:
        connection.execute(text("TRUNCATE houses RESTART IDENTITY"))


@pytest.fixture
def pg_app(make_settings) -> Iterator[FastAPI]:
    app = create_app(make_settings(database_url=URL))
    with TestClient(app):  # runs startup so the engine and tables exist
        reset(app)
    yield app
    with TestClient(app):
        reset(app)


@pytest.fixture
def pg(pg_app) -> Iterator[TestClient]:
    with TestClient(pg_app) as client:
        yield client


def test_the_database_is_really_postgres(pg, pg_app):
    with pg_app.state.engine.connect() as connection:
        version = connection.execute(text("SELECT version()")).scalar()

    assert "PostgreSQL" in str(version)
    assert pg.get("/api/health").json()["database"] == "ok"


def test_crud_cycle_on_postgres(pg, auth, house):
    created = pg.post("/api/houses", json=house, headers=auth).json()

    assert created["id"] == 1
    assert pg.get("/api/houses/1").json() == {"id": 1, **house}
    changed = pg.put("/api/houses/1", json=house | {"bedrooms": 5}, headers=auth)
    assert changed.json()["bedrooms"] == 5
    assert pg.delete("/api/houses/1", headers=auth).status_code == 204
    assert pg.get("/api/houses/1").status_code == 404


def test_values_survive_the_round_trip_exactly(pg, auth, house):
    sent = house | {"bathrooms": 2.25, "sqft_living": 13540, "zipcode": 98199}

    created = pg.post("/api/houses", json=sent, headers=auth).json()

    assert pg.get(f"/api/houses/{created['id']}").json() == {
        "id": created["id"],
        **sent,
    }


def test_ids_are_not_reused_after_a_delete(pg, auth, house):
    first = pg.post("/api/houses", json=house, headers=auth).json()["id"]
    pg.delete(f"/api/houses/{first}", headers=auth)

    second = pg.post("/api/houses", json=house, headers=auth).json()["id"]

    assert second > first


def test_pagination_is_ordered_and_counts_everything(pg, auth, house):
    for bedrooms in range(1, 6):
        pg.post("/api/houses", json=house | {"bedrooms": bedrooms}, headers=auth)

    page = pg.get("/api/houses", params={"limit": 2, "offset": 3}).json()

    assert page["total"] == 5
    assert [item["bedrooms"] for item in page["items"]] == [4, 5]


def test_data_outlives_the_application(make_settings, pg_app, auth, house):
    with TestClient(create_app(make_settings(database_url=URL))) as first:
        first.post("/api/houses", json=house, headers=auth)

    with TestClient(create_app(make_settings(database_url=URL))) as second:
        assert second.get("/api/houses").json()["total"] == 1
