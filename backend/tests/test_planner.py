import csv
import hashlib
import io
import sqlite3
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.gtfs import planner
from app.gtfs.schedule import gtfs_seconds, service_datetime
from app.gtfs.transfer_search import LINKS, TransferLink
from app.main import create_app
from app.walking import client as ors, store
from gtfs_fixtures import csv_text, files, setup_feed

INPUT = {"origin_stop_id": "skm:1", "destination_stop_id": "ztm:9", "departure_date": "2026-11-13", "departure_time": "17:00"}


def append(content, name, rows):
    old = list(csv.reader(io.StringIO(content[name])))
    content[name] = csv_text(",".join(old[0]), [*old[1:], *rows])


@pytest.fixture
def plan_api(tmp_path, setup_feed, monkeypatch):
    monkeypatch.setattr(ors, "open_request", lambda *a, **k: pytest.fail("Live ORS forbidden"))
    skm, ztm = files("skm"), files("ztm")
    append(skm, "stops.txt", [("7501", "Later interchange", 54, 18, 0, "")])
    append(skm, "stop_times.txt", [("a", "17:45:00", "17:46:00", "7501", 3, 0, 0)])
    append(ztm, "stops.txt", [("2135", "Other boarding 01", 54, 18, 0, ""), ("3001", "Later interchange 01", 54, 18, 0, ""), ("99", "Destination 02", 54, 18, 0, "")])
    specs = [("slow", "2001", "17:47:00", "18:20:00"), ("fast", "2135", "17:50:00", "18:00:00"),
             ("edge", "2001", "17:45:00", "17:50:00"), ("missed", "2001", "17:44:00", "17:49:00"),
             ("wrong-pole", "2002", "17:46:00", "17:48:00"), ("later-hub", "3001", "17:48:00", "17:55:00")]
    ztm["trips.txt"] = csv_text("route_id,service_id,trip_id,trip_headsign,direction_id", [("8", "S", t, "Destination", 0) for t, *_ in specs])
    ztm["stop_times.txt"] = csv_text("trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type",
                                      [row for trip, stop, dep, dest in specs for row in [(trip, dep, dep, stop, 1, 0, 0), (trip, dest, dest, "9", 2, 0, 0)]])
    append(ztm, "stop_times.txt", [(trip, "18:30:00", "18:30:00", "99", 3, 0, 0) for trip, *_ in specs])
    transit = setup_feed(skm=skm, ztm=ztm)
    walking = tmp_path / "walking.db"
    monkeypatch.setitem(LINKS, "fixture-later", TransferLink("fixture-later", "skm:7501", "ztm:3001"))
    for origin, target, seconds in [("skm:7500", "ztm:2001", 153.7), ("skm:7500", "ztm:2135", 120), ("skm:7501", "ztm:3001", 60)]:
        store.save_result(walking, origin, target, store.stop_pair(transit, origin, target),
                          {"status": "available", "walking_seconds": seconds, "distance_m": 200})
    with TestClient(create_app(transit, walking)) as api:
        yield api, transit, walking


def post(api, **kwargs):
    return api.post("/api/transit/journeys/plan", json={**INPUT, **kwargs})


def test_all_downstream_hubs_and_destination_arrival_ranking(plan_api, monkeypatch):
    api, transit, walking = plan_api
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (transit, walking)]
    response = post(api)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data == post(api).json()
    assert data["outcome"] == "found" and data["is_realtime"] is False
    assert {source["operator"] for source in data["sources"] if source["imported"] and source["is_realtime"] is False} == {"skm", "ztm"}
    chosen = data["results"][0]
    assert chosen["origin"]["stop_id"] == "skm:1"
    assert chosen["arrival"]["stop_id"] == "skm:7501"
    assert chosen["departure"]["trip_id"] == "ztm:later-hub"
    assert chosen["destination"]["arrival_at"].endswith("17:55:00+01:00")
    assert chosen["evaluation"]["margin_minutes"] == 2
    assert [item["departure"]["trip_id"] for item in data["results"]] == ["ztm:later-hub", "ztm:fast", "ztm:slow"]
    assert all(item["departure"]["trip_id"] != "ztm:wrong-pole" for item in data["results"])
    assert before == [hashlib.sha256(p.read_bytes()).hexdigest() for p in (transit, walking)]
    monkeypatch.delitem(LINKS, "fixture-later")
    assert post(api).json()["results"][0]["departure"]["trip_id"] == "ztm:fast"


@pytest.mark.parametrize("delay,margin", [(0, 2), (2, 0), (3, -1)])
def test_selected_journey_reuses_existing_pure_evaluation(plan_api, delay, margin):
    api, *_ = plan_api
    item = post(api).json()["results"][0]
    a, d = item["arrival"], item["departure"]
    body = {"link_id": item["link"]["id"], "arrival_trip_id": a["trip_id"], "arrival_service_date": a["service_date"],
            "arrival_stop_sequence": a["stop_sequence"], "departure_trip_id": d["trip_id"], "departure_route_id": d["route_id"],
            "departure_service_date": d["service_date"], "departure_stop_sequence": d["stop_sequence"], "delay_minutes": delay}
    response = api.post("/api/transit/transfers/search", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["evaluation"]["margin_minutes"] == margin


def test_edge_is_reachable_but_negative_margin_is_not_offered(plan_api, monkeypatch):
    api, *_ = plan_api
    monkeypatch.delitem(LINKS, "fixture-later")
    monkeypatch.delitem(LINKS, "gdansk-glowny-skm-pks-01")
    data = post(api).json()
    assert [x["departure"]["trip_id"] for x in data["results"]] == ["ztm:slow", "ztm:edge"]
    assert data["results"][1]["evaluation"]["margin_minutes"] == 0
    assert data["results"][1]["risk"] == "tight"


@pytest.mark.parametrize("overrides,outcome", [({"departure_time": "23:00"}, "no_skm"),
    ({"origin_stop_id": "skm:7501"}, "no_transfer_link"), ({"destination_stop_id": "ztm:10"}, "no_destination_service")])
def test_empty_states(plan_api, overrides, outcome):
    api, *_ = plan_api
    data = post(api, **overrides).json()
    assert data["outcome"] == outcome and not data["results"]


def test_missing_walking_and_no_approved_links(plan_api, monkeypatch, tmp_path):
    api, _, _ = plan_api
    api.app.state.walking_database_path = tmp_path / "missing.db"
    assert post(api).json()["outcome"] == "walking_unavailable"
    monkeypatch.setattr(planner, "LINKS", {})
    assert post(api).json()["outcome"] == "no_transfer_link"


def test_downstream_destination_only_and_calendar_exception(plan_api):
    api, *_ = plan_api
    assert post(api, destination_stop_id="ztm:2001").json()["outcome"] == "no_destination_service"
    assert post(api, departure_date="2026-11-16").json()["outcome"] == "no_skm"
    assert post(api, departure_date="2026-11-14").json()["outcome"] == "found"


def test_origin_cannot_be_its_own_skm_alighting_stop(plan_api):
    api, *_ = plan_api
    data = post(api, origin_stop_id="skm:7500").json()
    assert data["outcome"] == "found"
    assert all(item["arrival"]["stop_id"] == "skm:7501" for item in data["results"])


@pytest.mark.parametrize("stop_id,column,outcome", [("ztm:9", "drop_off_type", "no_destination_service"),
    ("skm:1", "pickup_type", "no_skm")])
def test_boarding_and_alighting_permissions(plan_api, stop_id, column, outcome):
    api, transit, _ = plan_api
    with sqlite3.connect(transit) as connection:
        connection.execute(f"UPDATE gtfs_stop_times SET {column}=1 WHERE stop_id=?", (stop_id,))
    assert post(api).json()["outcome"] == outcome


@pytest.mark.parametrize("body", [{"origin_stop_id": "ztm:1"}, {"destination_stop_id": "ztm:missing"},
    {"departure_time": "25:00"}, {"departure_date": "2027-01-01"}, {"max_results": 4},
    {"origin_stop_ids": ["skm:1"]}, {"departure_offset": "+02:00"}, {"departure_date": "2026-03-29", "departure_time": "02:30"}])
def test_validation_and_coverage(plan_api, body):
    api, *_ = plan_api
    assert post(api, **body).status_code in (404, 422)


def test_grouped_poles_no_silent_name_selection(plan_api):
    api, *_ = plan_api
    data = api.get("/api/transit/journeys/stops", params={"operator": "ztm", "query": "destination"}).json()
    assert any(len(group["stops"]) == 2 for group in data["groups"])
    body = {key: value for key, value in INPUT.items() if key != "destination_stop_id"}
    response = api.post("/api/transit/journeys/plan", json={**body, "destination_stop_ids": ["ztm:99", "ztm:9", "ztm:9"]})
    assert response.status_code == 200 and response.json()["destination_stop_ids"] == ["ztm:9", "ztm:99"]
    assert all(item["destination"]["stop_id"] == "ztm:9" for item in response.json()["results"])
    assert api.get("/api/transit/journeys/stops?operator=ztm&limit=1").json()["has_more"]


def test_candidate_limits_are_errors_not_partial_best_results(plan_api, monkeypatch):
    api, *_ = plan_api
    monkeypatch.setattr(planner, "MAX_COMBINATIONS", 1)
    response = post(api)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "search_limit_exceeded"
    monkeypatch.setattr(planner, "MAX_TRAINS", 0)
    assert post(api).status_code == 409


@pytest.mark.parametrize("state", ["stale", "no_route"])
def test_non_current_walking_is_excluded(plan_api, state):
    api, transit, walking = plan_api
    for origin, target in [("skm:7500", "ztm:2001"), ("skm:7500", "ztm:2135"), ("skm:7501", "ztm:3001")]:
        store.save_result(walking, origin, target, store.stop_pair(transit, origin, target),
                          {"status": "no_route", "walking_seconds": None, "distance_m": None} if state == "no_route" else
                          {"status": "available", "walking_seconds": 180, "distance_m": 200},
                          now=datetime.now(timezone.utc) - timedelta(days=31) if state == "stale" else None)
    data = post(api).json()
    assert data["outcome"] == "walking_unavailable" and not data["results"]
    assert any(item["status"] == state for item in data["excluded_links"])


@pytest.mark.parametrize("day,offset", [("2026-10-25", "+02:00"), ("2026-10-25", "+01:00")])
def test_repeated_dst_wall_clock_requires_explicit_offset(day, offset):
    value = {**INPUT, "departure_date": day, "departure_time": "02:30"}
    with pytest.raises(planner.SearchError, match="dwukrotnie"):
        planner.requested_instant(planner.PlanInput(**value))
    actual = planner.requested_instant(planner.PlanInput(**value, departure_offset=offset))
    assert actual.isoformat().endswith(offset)


@pytest.mark.parametrize("day,arrival,departures,start", [
    ("2026-11-13", "23:58:00", ("24:03:00", "25:00:00"), "23:40"),
    ("2026-10-25", "02:55:00", ("03:00:00",), "02:30"),
    ("2026-03-29", "02:55:00", ("03:00:00",), "01:30"),
])
def test_midnight_extended_gtfs_and_dst_end_to_end(tmp_path, setup_feed, day, arrival, departures, start):
    skm, ztm = files("skm", arrival=arrival), files("ztm", departures_at=departures)
    # Enable these synthetic services explicitly, including DST Sundays.
    for feed in (skm, ztm):
        feed["calendar_dates.txt"] += f'S,{day.replace("-", "")},1\n'
    transit = setup_feed(skm=skm, ztm=ztm)
    walking = tmp_path / "walking.db"
    store.save_result(walking, "skm:7500", "ztm:2001", store.stop_pair(transit, "skm:7500", "ztm:2001"),
                      {"status": "available", "walking_seconds": 180, "distance_m": 200})
    with TestClient(create_app(transit, walking)) as api:
        data = post(api, departure_date=day, departure_time=start, **({"departure_offset": "+01:00"} if day == "2026-10-25" else {})).json()
        assert data["outcome"] == "found", data
        result = data["results"][0]
        assert result["arrival"]["arrival_at"] == service_datetime(date.fromisoformat(day), gtfs_seconds(arrival)).isoformat()
        assert planner.instant(result["destination"]["arrival_at"]) >= planner.instant(result["departure"]["departure_at"])
