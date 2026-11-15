import csv
import hashlib
import io
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.gtfs import suggestions
from app.main import create_app
from app.walking import client as ors, store
from gtfs_fixtures import csv_text, files, setup_feed


INPUT = {"arrival_stop_id": "skm:7500", "arrival_trip_id": "skm:a", "arrival_service_date": "2026-11-13",
         "arrival_stop_sequence": 2, "query": "8"}


def append_rows(content, name, rows):
    original = list(csv.reader(io.StringIO(content[name])))
    content[name] = csv_text(",".join(original[0]), [*original[1:], *rows])


@pytest.fixture
def suggestion_api(tmp_path, setup_feed, monkeypatch):
    monkeypatch.setattr(ors, "open_request", lambda *args, **kwargs: pytest.fail("Live ORS forbidden"))
    content = files("ztm")
    content["stops.txt"] = content["stops.txt"].replace(",Destination,", ",Uniwersytet Gdański,")
    append_rows(content, "stops.txt", [("2135", "Dworzec PKS 01", 54, 18, 0, ""),
                                     ("2136", "Dworzec PKS 02", 54, 18, 0, ""),
                                     ("1021", "Dworzec Główny 08", 54, 18, 0, "")])
    append_rows(content, "trips.txt", [("8", "S", "edge", "Oliwa", 0),
                                     ("8", "S", "short", "Oliwa", 0),
                                     ("other", "S", "variant", "Oliwa", 1)])
    append_rows(content, "stop_times.txt", [
        ("edge", "17:45:30", "17:45:30", "2001", 1, 0, 0),
        ("edge", "17:50:30", "17:50:30", "9", 2, 0, 0),
        ("short", "17:40:00", "17:40:00", "1", 1, 0, 0),
        ("short", "17:46:00", "17:46:00", "2135", 2, 0, 0),
        ("short", "17:50:00", "17:50:00", "9", 3, 0, 0),
        ("variant", "17:45:00", "17:45:00", "2135", 1, 0, 0),
        ("variant", "17:50:00", "17:50:00", "10", 2, 0, 0),
    ])
    transit = setup_feed(ztm=content)
    walking = tmp_path / "walking.db"
    for stop, seconds in (("ztm:2001", 153.7), ("ztm:2135", 120)):
        store.save_result(walking, "skm:7500", stop, store.stop_pair(transit, "skm:7500", stop),
                          {"status": "available", "walking_seconds": seconds, "distance_m": 200})
    with TestClient(create_app(transit, walking)) as api:
        yield api, transit, walking


def post(api, **overrides):
    return api.post("/api/transit/transfers/suggest", json={**INPUT, **overrides})


def test_ranking_uses_safe_margin_then_waiting_across_exact_poles(suggestion_api):
    api, _, _ = suggestion_api
    data = post(api).json()
    chosen = data["recommendation"]
    assert data["outcome"] == "recommended"
    assert chosen["departure"]["trip_id"] == "ztm:short"
    assert chosen["departure"]["stop_id"] == "ztm:2135"
    assert chosen["evaluation"]["margin_minutes"] == 2
    assert chosen["link"]["walking_minutes"] == 2
    assert chosen["link"]["walking"]["estimate"]["confidence"] == "estimated"
    assert "2 min" in data["reason"]
    assert data["results"][-1]["evaluation"]["margin_minutes"] < 2
    assert data == post(api).json()


@pytest.mark.parametrize("query,kind", [("8", "line"), ("Oliwa", "direction"), ("8 Oliwa", "direction"), ("Uniwersytet gdanski", "stop")])
def test_line_direction_and_downstream_destination(suggestion_api, query, kind):
    api, _, _ = suggestion_api
    data = post(api, query=query).json()
    assert data["recommendation"]["match"]["kind"] == kind
    if kind == "stop":
        assert all(item["match"]["stop_id"] == "ztm:9" for item in data["results"])
        assert all(item["departure"]["trip_id"] != "ztm:variant" for item in data["results"])


@pytest.mark.parametrize("query", ["Earlier stop", "Nonexistent destination", "18"])
def test_no_match_and_no_boarding_at_a_previous_stop(suggestion_api, query):
    api, _, _ = suggestion_api
    data = post(api, query=query).json()
    assert data["outcome"] == "no_match" and data["recommendation"] is None and not data["results"]


def test_blank_query_proposes_directions_without_guessing_a_destination(suggestion_api):
    api, _, _ = suggestion_api
    data = post(api, query="").json()
    assert data["outcome"] == "choose_destination"
    assert data["recommendation"] is None and data["results"] == []
    assert data["directions"] == [{"line": "8", "direction": "Oliwa", "query": "8 Oliwa"}]


def test_terminal_stops_and_numeric_destination_names():
    departure = {"line": "8", "direction": "Oliwa"}
    downstream = [{"stop_id": "ztm:9", "stop_name": "Dywizjonu 303"}]
    assert suggestions.match_course("Dywizjonu 303", departure, downstream)["stop_id"] == "ztm:9"
    assert suggestions.match_course("8", departure, []) is None
    assert suggestions.match_course("18 Oliwa", departure, downstream) is None
    assert suggestions.match_course("N1", {**departure, "line": "N10"}, downstream) is None
    assert suggestions.match_course("N1 Oliwa", {**departure, "line": "N10"}, downstream) is None


def test_ties_are_deterministic_and_do_not_depend_on_input_order():
    def candidate(trip, stop, margin):
        return {"evaluation": {"margin_minutes": margin}, "link": {"walking_minutes": 3, "id": stop},
                "departure": {"departure_at": "2026-11-13T17:51:00+01:00", "route_id": "ztm:8",
                              "trip_id": trip, "service_date": "2026-11-13", "stop_sequence": 1}}
    candidates = [candidate("ztm:b", "link-b", 2), candidate("ztm:a", "link-a", 2), candidate("ztm:c", "link-c", 1.99)]
    assert sorted(candidates, key=suggestions.ranking_key) == sorted(reversed(candidates), key=suggestions.ranking_key)
    assert sorted(candidates, key=suggestions.ranking_key)[0]["departure"]["trip_id"] == "ztm:a"


def test_delay_boundaries_and_unreachable_courses(suggestion_api):
    api, _, _ = suggestion_api
    for delay, margin, status in [(0, 2, "Zdążysz"), (0.01, 1.99, "Zdążysz"), (2, 0, "Na styk"), (3, -1, "Nie zdążysz")]:
        data = post(api, query="Uniwersytet gdanski").json()
        chosen = next(item for item in data["results"] if item["departure"]["trip_id"] == "ztm:short")
        departure = chosen["departure"]
        response = api.post("/api/transit/transfers/search", json={
            "link_id": chosen["link"]["id"], "arrival_trip_id": INPUT["arrival_trip_id"],
            "arrival_service_date": INPUT["arrival_service_date"], "arrival_stop_sequence": 2,
            "departure_route_id": departure["route_id"], "departure_trip_id": departure["trip_id"],
            "departure_service_date": departure["service_date"], "departure_stop_sequence": departure["stop_sequence"], "delay_minutes": delay})
        assert response.status_code == 200
        assert response.json()["results"][0]["evaluation"]["margin_minutes"] == margin
        assert response.json()["results"][0]["evaluation"]["status"] == status
    # This exact destination is only visited by the early variant, with 1 min margin.
    data = post(api, query="Other destination", delay_minutes=2).json()
    assert data["outcome"] == "no_reachable" and data["recommendation"] is None


@pytest.mark.parametrize("state", ["missing", "stale", "no_route"])
def test_walking_cache_is_required_without_fallback(suggestion_api, monkeypatch, state):
    api, _, _ = suggestion_api
    monkeypatch.setattr(suggestions, "walking_for_link", lambda path, walking, link, *args: {"status": state})
    data = post(api).json()
    assert data["outcome"] == "walking_unavailable" and data["recommendation"] is None
    assert len(data["excluded_links"]) == 4
    assert all(item["status"] == state for item in data["excluded_links"])


def test_limits_errors_and_read_only(suggestion_api, monkeypatch):
    api, transit, walking = suggestion_api
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in (transit, walking)]
    for patch in ({"limit": 0}, {"limit": 21}, {"query": "x" * 121}, {"delay_minutes": -1},
                  {"arrival_stop_sequence": True}, {"arrival_service_date": "2026-02-30"}):
        assert post(api, **patch).status_code == 422
    assert post(api, arrival_stop_id="skm:other").status_code == 404
    assert post(api, arrival_trip_id="skm:unknown").status_code == 404
    assert post(api, arrival_service_date="2027-01-01").json()["detail"]["code"] == "feed_out_of_range"
    assert post(api, arrival_service_date="2026-11-16").json()["detail"]["code"] == "arrival_not_running"
    assert post(api, arrival_service_date="2026-11-15").json()["detail"]["code"] == "arrival_not_running"
    assert post(api, arrival_service_date="2026-11-14").status_code == 200
    result = post(api, limit=1).json()
    assert len(result["results"]) == 1 and result["has_more"]
    monkeypatch.setattr(suggestions, "stop_departures", lambda *args: [{}] * 2001)
    assert post(api).status_code == 409
    assert before == [hashlib.sha256(path.read_bytes()).hexdigest() for path in (transit, walking)]


@pytest.mark.parametrize("day,arrival,departure", [
    ("2026-11-13", "23:58:00", "24:07:00"),
    ("2026-03-29", "01:58:00", "02:07:00"),
    ("2026-10-25", "01:58:00", "02:07:00"),
])
def test_midnight_extended_hours_and_dst(tmp_path, setup_feed, day, arrival, departure):
    skm, ztm = files("skm", arrival=arrival), files("ztm", departures_at=(departure,))
    for content in (skm, ztm):
        content["calendar.txt"] = content["calendar.txt"].replace(",1,1,1,1,1,0,0,", ",1,1,1,1,1,1,1,")
    transit = setup_feed(skm, ztm)
    walking = tmp_path / "walking.db"
    store.save_result(walking, "skm:7500", "ztm:2001", store.stop_pair(transit, "skm:7500", "ztm:2001"),
                      {"status": "available", "walking_seconds": 153.7, "distance_m": 213.5})
    with TestClient(create_app(transit, walking)) as api:
        data = post(api, arrival_service_date=day).json()
    chosen = data["recommendation"]
    assert chosen["evaluation"]["margin_minutes"] == 6
    assert chosen["departure"]["service_date"] == day
    assert datetime.fromisoformat(chosen["departure"]["departure_at"]).utcoffset() is not None
