import pytest
from fastapi.testclient import TestClient

from kc_house.api.main import create_app


def test_writes_without_the_key_are_unauthorized(client, house):
    wrong = {"X-API-Key": "nope"}

    assert client.post("/api/houses", json=house).status_code == 401
    assert client.post("/api/houses", json=house, headers=wrong).status_code == 401
    assert client.delete("/api/houses/1", headers=wrong).status_code == 401


def test_reads_never_need_a_key(client):
    assert client.get("/api/houses").status_code == 200
    assert client.get("/api/zipcodes").status_code == 200


def test_writes_are_disabled_when_no_key_is_configured(make_settings, house):
    with TestClient(create_app(make_settings(api_key=None))) as client:
        response = client.post("/api/houses", json=house)

    assert response.status_code == 403


def test_open_writes_must_be_asked_for_explicitly(make_settings, house):
    settings = make_settings(api_key=None, open_writes=True)

    with TestClient(create_app(settings)) as client:
        response = client.post("/api/houses", json=house)

    assert response.status_code == 201


def test_health_reports_model_and_database(client):
    body = client.get("/api/health").json()

    assert body == {"status": "ok", "model": body["model"], "database": "ok"}
    assert body["model"].startswith("abc1234")


def test_estimates_keep_working_when_the_database_is_down(make_settings, house):
    settings = make_settings(database_url="sqlite:////no/such/folder/x.db")

    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json()["database"] == "unavailable"
        assert client.post("/api/estimate", json=house).status_code == 200
        assert client.get("/api/houses").status_code == 503


def test_the_app_refuses_to_start_without_a_model(make_settings, tmp_path):
    settings = make_settings(model_dir=tmp_path)

    with (
        pytest.raises(FileNotFoundError, match="kc-train"),
        TestClient(create_app(settings)),
    ):
        pass


def test_zipcodes_lists_the_trained_codes(client):
    codes = client.get("/api/zipcodes").json()

    assert 98103 in codes
    assert codes == sorted(codes)


def test_every_response_carries_a_request_id_and_honours_a_safe_incoming_one(client):
    assert len(client.get("/api/health").headers["x-request-id"]) == 12
    sent = client.get("/api/health", headers={"X-Request-ID": "abc-123"})
    assert sent.headers["x-request-id"] == "abc-123"
    unsafe = client.get("/api/health", headers={"X-Request-ID": "bad id!"})
    assert unsafe.headers["x-request-id"] != "bad id!"


def test_meta_exposes_what_the_page_needs(client):
    body = client.get("/api/meta").json()

    assert body["inputs"][0] == "bedrooms"
    assert body["model"]["r2"] == 0.84
    assert "github_url" in body
