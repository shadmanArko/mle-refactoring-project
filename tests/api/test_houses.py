import pytest


@pytest.fixture
def create(client, auth, house):
    def make(**overrides):
        return client.post("/api/houses", json=house | overrides, headers=auth)

    return make


def test_full_crud_cycle(client, auth, house, create):
    created = create()
    house_id = created.json()["id"]

    assert created.status_code == 201
    assert client.get(f"/api/houses/{house_id}").json() == {"id": house_id, **house}

    updated = client.put(
        f"/api/houses/{house_id}", json=house | {"bedrooms": 4}, headers=auth
    )
    assert updated.status_code == 200
    assert updated.json()["bedrooms"] == 4

    assert client.delete(f"/api/houses/{house_id}", headers=auth).status_code == 204
    assert client.get(f"/api/houses/{house_id}").status_code == 404


def test_listing_is_paginated_with_a_total(client, create):
    for bedrooms in range(5):
        create(bedrooms=bedrooms)

    page = client.get("/api/houses", params={"limit": 2, "offset": 2}).json()

    assert page["total"] == 5
    assert [item["bedrooms"] for item in page["items"]] == [2, 3]
    assert (page["limit"], page["offset"]) == (2, 2)


def test_missing_houses_return_404_for_every_verb(client, auth, house):
    assert client.get("/api/houses/999").status_code == 404
    assert client.put("/api/houses/999", json=house, headers=auth).status_code == 404
    assert client.delete("/api/houses/999", headers=auth).status_code == 404
    assert client.get("/api/houses/999/estimate").status_code == 404


def test_invalid_house_is_rejected_and_not_stored(client, create):
    assert create(grade=99).status_code == 422
    assert create(zipcode=98009).status_code == 422

    assert client.get("/api/houses").json()["total"] == 0


def test_a_stored_house_can_be_estimated(client, create):
    house_id = create().json()["id"]

    response = client.get(f"/api/houses/{house_id}/estimate")

    assert response.status_code == 200
    assert response.json()["estimate"] > 0
