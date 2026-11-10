from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import event

from app.transfer_logic import evaluate_transfer


@pytest.fixture
def transfer_data():
    return {
        "arrival_at": "2026-11-10T17:42:00+01:00",
        "departure_at": "2026-11-10T17:51:00+01:00",
        "walking_minutes": 3,
        "delay_minutes": 0,
        "next_departures": ["2026-11-10T18:03:00+01:00"],
    }


def domain_input(data):
    return {
        **data,
        "arrival_at": datetime.fromisoformat(data["arrival_at"]),
        "departure_at": datetime.fromisoformat(data["departure_at"]),
        "next_departures": [datetime.fromisoformat(value) for value in data["next_departures"]],
    }


@pytest.mark.parametrize("delay,margin,status,plan_b", [
    (0, 6, "Zdążysz", "not_needed"),
    (5.5, 0.5, "Zdążysz", "not_needed"),
    (6, 0, "Na styk", "not_needed"),
    (6.5, -0.5, "Nie zdążysz", "available"),
    (8, -2, "Nie zdążysz", "available"),
])
def test_reference_domain_and_api(client, transfer_data, delay, margin, status, plan_b):
    data = {**transfer_data, "delay_minutes": delay}
    result = evaluate_transfer(**domain_input(data))
    assert result.margin_minutes == margin
    assert result.status == status
    response = client.post("/api/transfers/evaluate", json=data)
    assert response.status_code == 200
    assert response.json() == {
        "margin_minutes": margin,
        "delay_threshold_minutes": 6,
        "status": status,
        "has_safe_margin": True,
        "expected_stop_arrival_at": result.expected_stop_arrival_at.isoformat(),
        "plan_b_status": plan_b,
        "plan_b_departure_at": transfer_data["next_departures"][0] if plan_b == "available" else None,
    }


@pytest.mark.parametrize("walking,threshold,status,safe", [
    (5, 4, "Zdążysz", True), (9, 0, "Na styk", False), (10, -1, "Nie zdążysz", False),
])
def test_initial_margin(client, transfer_data, walking, threshold, status, safe):
    response = client.post("/api/transfers/evaluate", json={**transfer_data, "walking_minutes": walking})
    assert response.status_code == 200
    assert response.json()["delay_threshold_minutes"] == threshold
    assert response.json()["margin_minutes"] == threshold
    assert response.json()["status"] == status
    assert response.json()["has_safe_margin"] is safe


@pytest.mark.parametrize("arrival,departure,expected", [
    ("2026-11-10T23:58:00+01:00", "2026-11-11T00:07:00+01:00", "2026-11-11T00:01:00+01:00"),
    ("2026-03-29T01:58:00+01:00", "2026-03-29T03:07:00+02:00", "2026-03-29T03:01:00+02:00"),
    ("2026-10-25T02:58:00+02:00", "2026-10-25T02:07:00+01:00", "2026-10-25T02:01:00+01:00"),
])
def test_midnight_and_dst(client, transfer_data, arrival, departure, expected):
    data = {**transfer_data, "arrival_at": arrival, "departure_at": departure, "next_departures": []}
    response = client.post("/api/transfers/evaluate", json=data)
    assert response.status_code == 200
    assert response.json()["margin_minutes"] == 6
    assert response.json()["expected_stop_arrival_at"] == expected
    # The same ZoneInfo instance must also work (Python wall-time subtraction differs).
    inputs = domain_input(data)
    for key in ("arrival_at", "departure_at"):
        inputs[key] = inputs[key].astimezone(ZoneInfo("Europe/Warsaw"))
    assert evaluate_transfer(**inputs).margin_minutes == 6


@pytest.mark.parametrize("departures,delay,selected", [
    ([], 8, None),
    (["2026-11-10T18:03:00+01:00"], 19, None),
    (["2026-11-10T18:15:00+01:00", "2026-11-10T18:03:00+01:00"], 18, "2026-11-10T18:03:00+01:00"),
    (["2026-11-10T17:52:00+01:00", "2026-11-10T18:03:00+01:00"], 8, "2026-11-10T18:03:00+01:00"),
])
def test_alternatives(client, transfer_data, departures, delay, selected):
    data = {**transfer_data, "next_departures": departures, "delay_minutes": delay}
    inputs = domain_input(data)
    original = inputs["next_departures"].copy()
    result = evaluate_transfer(**inputs)
    assert inputs["next_departures"] == original
    assert result == evaluate_transfer(**inputs)
    response = client.post("/api/transfers/evaluate", json=data)
    assert response.status_code == 200
    assert response.json()["plan_b_departure_at"] == selected
    assert response.json()["plan_b_status"] == ("available" if selected else "unavailable")


def test_plan_b_compares_instants_at_fall_back(client, transfer_data):
    data = {**transfer_data,
        "arrival_at": "2026-10-25T02:50:00+02:00",
        "departure_at": "2026-10-25T02:54:00+02:00",
        "delay_minutes": 4,
        "next_departures": ["2026-10-25T02:05:00+01:00", "2026-10-25T02:59:00+02:00"],
    }
    response = client.post("/api/transfers/evaluate", json=data)
    assert response.status_code == 200
    assert response.json()["plan_b_departure_at"] == "2026-10-25T02:59:00+02:00"


@pytest.mark.parametrize("change", [
    {"delay_minutes": -1}, {"delay_minutes": True}, {"delay_minutes": "8"},
    {"delay_minutes": None}, {"delay_minutes": 1e300},
    {"walking_minutes": -1}, {"walking_minutes": True}, {"walking_minutes": 1.5},
    {"arrival_at": "2026-11-10T17:42:00"},
    {"arrival_at": "2026-03-29T02:30:00+01:00"},
    {"arrival_at": "2026-11-10T17:42:00+02:00"},
    {"departure_at": "bad"}, {"next_departures": None},
    {"next_departures": ["2026-11-10T17:51:00+01:00"]},
    {"next_departures": ["2026-11-10T17:50:00+01:00"]},
    {"next_departures": ["2026-11-10T18:03:00"]}, {"unexpected": 1},
    {"arrival_at": "9999-12-31T23:58:00+01:00", "next_departures": []},
])
def test_invalid_evaluation(client, transfer_data, change):
    response = client.post("/api/transfers/evaluate", json={**transfer_data, **change})
    assert response.status_code == 422
    assert response.json()["detail"]


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_delay(client, transfer_data, value):
    import json

    body = json.dumps(transfer_data).replace('"delay_minutes": 0', f'"delay_minutes": {value}')
    assert client.post("/api/transfers/evaluate", content=body, headers={"Content-Type": "application/json"}).status_code == 422


def test_missing_fields(client):
    assert client.post("/api/transfers/evaluate", json={}).status_code == 422


@pytest.mark.parametrize("change", [
    {"delay_minutes": -1}, {"delay_minutes": float("nan")}, {"delay_minutes": float("inf")},
    {"arrival_at": datetime(2026, 11, 10, 17, 42)},
])
def test_domain_rejects_invalid_values(transfer_data, change):
    with pytest.raises(ValueError):
        evaluate_transfer(**{**domain_input(transfer_data), **change})


def test_evaluation_does_not_access_or_modify_database(client, scenario_data, transfer_data):
    created = client.post("/api/scenarios", json=scenario_data).json()
    engine = client.app.state.engine
    database = Path(engine.url.database)
    before = database.read_bytes()

    def forbid_sql(*args):
        raise AssertionError("Evaluation must not execute SQL")

    event.listen(engine, "before_cursor_execute", forbid_sql)
    try:
        for delay in (0, 6, 8, -1):
            response = client.post("/api/transfers/evaluate", json={**transfer_data, "delay_minutes": delay})
            assert response.status_code == (422 if delay < 0 else 200)
    finally:
        event.remove(engine, "before_cursor_execute", forbid_sql)
    assert database.read_bytes() == before
    assert client.get("/api/scenarios").json() == [created]
