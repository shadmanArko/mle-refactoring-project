import pytest


@pytest.fixture
def answers(house) -> dict:
    return house | {"waterfront": False}


def test_estimate_returns_a_price_with_an_honest_range(client, answers):
    response = client.post("/api/estimate", json=answers)

    body = response.json()
    assert response.status_code == 200
    assert body["low"] < body["estimate"] < body["high"]
    assert body["estimate"] % 1000 == 0
    assert body["coverage"] == 0.8
    assert body["typical_error_pct"] == 10.5
    assert body["model_version"].startswith("abc1234")
    assert "not an appraisal" in body["note"]


def test_a_bigger_house_is_estimated_higher(client, answers):
    small = client.post("/api/estimate", json=answers | {"sqft_living": 900}).json()
    large = client.post("/api/estimate", json=answers | {"sqft_living": 4000}).json()

    assert large["estimate"] > small["estimate"]


def test_waterfront_is_optional_and_defaults_to_no(client, house):
    response = client.post("/api/estimate", json=house)

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("bedrooms", -1),
        ("bedrooms", 40),
        ("bathrooms", 2.1),
        ("sqft_living", 50),
        ("grade", 20),
        ("zipcode", 10001),
    ],
)
def test_out_of_range_answers_are_rejected(client, answers, field, value):
    response = client.post("/api/estimate", json=answers | {field: value})

    assert response.status_code == 422


def test_a_zipcode_the_model_never_saw_gets_a_helpful_message(client, answers):
    # Inside the allowed numeric range, but not a zip code in the training data.
    response = client.post("/api/estimate", json=answers | {"zipcode": 98009})

    assert response.status_code == 422
    assert "/api/zipcodes" in response.json()["detail"]


def test_missing_answers_are_rejected(client):
    response = client.post("/api/estimate", json={"bedrooms": 3})

    assert response.status_code == 422
