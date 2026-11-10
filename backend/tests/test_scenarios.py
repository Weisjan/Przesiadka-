from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.main import create_app


def test_crud(client, scenario_data):
    assert client.get("/api/scenarios").json() == []
    response = client.post("/api/scenarios", json=scenario_data)
    assert response.status_code == 201
    created = response.json()
    url = f"/api/scenarios/{created['id']}"
    assert response.headers["Location"] == url
    assert created == {**scenario_data, "id": created["id"]}
    assert client.get(url).json() == created
    assert client.get("/api/scenarios").json() == [created]

    changed = {**scenario_data, "name": "Powrót", "walking_minutes": 0, "next_departures": []}
    response = client.put(url, json=changed)
    assert response.status_code == 200
    assert response.json() == {**changed, "id": created["id"]}
    assert client.get(url).json() == response.json()
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404
    assert client.get("/api/scenarios").json() == []


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_missing_scenario(client, scenario_data, method):
    kwargs = {"json": scenario_data} if method == "put" else {}
    response = getattr(client, method)("/api/scenarios/9999", **kwargs)
    assert response.status_code == 404
    assert response.json()["detail"] == "Nie znaleziono scenariusza."


@pytest.mark.parametrize("change", [
    {"name": "  "}, {"name": "x" * 121}, {"interchange": ""}, {"arrival_line": ""},
    {"departure_line": ""}, {"direction": ""}, {"name": None},
    {"walking_minutes": -1}, {"walking_minutes": 1.5}, {"walking_minutes": True},
    {"walking_minutes": 1441}, {"walking_minutes": "5"},
    {"arrival_at": "2026-11-10T08:00:00"}, {"arrival_at": 1794294000},
    {"arrival_at": "2026-11-10T08:00:00+02:00"},
    {"arrival_at": "2026-07-10T08:00:00+01:00"},
    {"arrival_at": "2026-03-29T02:30:00+01:00"},
    {"arrival_at": "2026-03-29T02:30:00+02:00"},
    {"arrival_at": "9999-12-31T23:59:00+00:00"},
    {"arrival_at": "0001-01-01T00:00:00+01:24"},
    {"departure_at": "not-a-date"}, {"next_departures": None},
    {"next_departures": ["2026-11-10T08:07:00+01:00"]},
    {"next_departures": ["2026-11-10T08:27:00+01:00", "2026-11-10T08:17:00+01:00"]},
    {"next_departures": ["2026-11-10T08:17:00+01:00"] * 2},
    {"unexpected": "value"},
])
def test_invalid_input_does_not_change_data(client, scenario_data, change):
    created = client.post("/api/scenarios", json=scenario_data).json()
    invalid = {**scenario_data, **change}
    assert client.post("/api/scenarios", json=invalid).status_code == 422
    assert client.put(f"/api/scenarios/{created['id']}", json=invalid).status_code == 422
    assert client.get("/api/scenarios").json() == [created]


def test_put_requires_complete_scenario(client, scenario_data):
    created = client.post("/api/scenarios", json=scenario_data).json()
    assert client.put(f"/api/scenarios/{created['id']}", json={"name": "Zmiana"}).status_code == 422
    assert client.get(f"/api/scenarios/{created['id']}").json() == created


def test_mutation_does_not_change_other_scenarios(client, scenario_data):
    first = client.post("/api/scenarios", json=scenario_data).json()
    second = client.post("/api/scenarios", json={**scenario_data, "name": "Drugi"}).json()
    second_url = f"/api/scenarios/{second['id']}"
    assert client.put(second_url, json={**scenario_data, "name": "Zmiana drugiego"}).status_code == 200
    assert client.get(f"/api/scenarios/{first['id']}").json() == first
    assert client.delete(second_url).status_code == 204
    assert client.get("/api/scenarios").json() == [first]


def test_database_failure_is_reported_without_internal_details(client):
    SQLModel.metadata.drop_all(client.app.state.engine)
    response = client.get("/api/scenarios")
    assert response.status_code == 503
    assert response.json() == {"detail": "Baza danych jest niedostępna. Spróbuj ponownie."}


def test_warsaw_dst_and_midnight_roundtrip(client, scenario_data):
    data = {**scenario_data,
        "arrival_at": "2026-10-25T02:55:00+02:00",
        "departure_at": "2026-10-25T02:10:00+01:00",
        "next_departures": ["2026-10-26T00:05:00+01:00"],
    }
    response = client.post("/api/scenarios", json=data)
    assert response.status_code == 201
    assert response.json() == {**data, "id": response.json()["id"]}


def test_storage_survives_app_restart(tmp_path: Path, scenario_data):
    database = tmp_path / "restart.db"
    with TestClient(create_app(database)) as first:
        created = first.post("/api/scenarios", json=scenario_data).json()
    with TestClient(create_app(database)) as second:
        url = f"/api/scenarios/{created['id']}"
        assert second.get(url).json() == created
        updated = second.put(url, json={**scenario_data, "name": "Po restarcie"}).json()
    with TestClient(create_app(database)) as third:
        assert third.get(url).json() == updated
        assert third.delete(url).status_code == 204
    with TestClient(create_app(database)) as fourth:
        assert fourth.get("/api/scenarios").json() == []


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_crud_cors_preflight(client, origin, method):
    response = client.options("/api/scenarios", headers={
        "Origin": origin, "Access-Control-Request-Method": method,
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
