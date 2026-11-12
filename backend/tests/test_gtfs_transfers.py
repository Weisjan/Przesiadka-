import csv
import io
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.gtfs import transfer_search
from app.gtfs.importer import import_feed
from app.gtfs.schedule import gtfs_seconds
from app.gtfs.store import departures
from app.gtfs.transfer_search import LINK
from app.main import create_app


PATH = "/api/transit/transfers/search"
REQUEST = {"link_id": LINK.id, "arrival_trip_id": "skm:a", "arrival_service_date": "2026-11-12",
           "departure_route_id": "ztm:8", "walking_minutes": 3, "limit": 1}


def csv_text(header, rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(header.split(","))
    writer.writerows(rows)
    return output.getvalue()


def clock(seconds):
    return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"


def files(operator, arrival="17:42:00", departures_at=("17:51:00", "18:03:00", "18:15:00")):
    stops = [("H", "Station", 54, 18, 1, ""), ("1", "Earlier stop", 54, 18, 0, ""),
             ("7500", "GDAŃSK GŁÓWNY", 54, 18, 0, "H"),
             ("2001", "Dworzec Główny 01", 54, 18, 0, "H"),
             ("2002", "Dworzec Główny 01", 54, 18, 0, "H"),
             ("9", "Destination", 54, 18, 0, ""), ("10", "Other destination", 54, 18, 0, "")]
    trips, times = [], []
    if operator == "skm":
        trips = [("rail", "S", "a", "Gdańsk Śródmieście", "")]
        seconds = gtfs_seconds(arrival)
        times = [("a", clock(seconds - 600), clock(seconds - 600), "1", 1, 0, 0),
                 ("a", arrival, clock(seconds + 60), "7500", 2, 0, 0)]
    else:
        for index, departure in enumerate(departures_at):
            trip_id = chr(97 + index)
            trips.append(("8", "S", trip_id, "Oliwa", 0))
            times.extend([(trip_id, departure, departure, "2001", 1, 0, 0),
                          (trip_id, clock(gtfs_seconds(departure) + 300), clock(gtfs_seconds(departure) + 300), "9", 2, 0, 0)])
    return {
        "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\nA,Fixture,https://example.invalid,Europe/Warsaw\n",
        "stops.txt": csv_text("stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station", stops),
        "routes.txt": "route_id,agency_id,route_short_name,route_type\nrail,A,SKM,2\n8,A,8,3\nother,A,8,3\n",
        "trips.txt": csv_text("route_id,service_id,trip_id,trip_headsign,direction_id", trips),
        "stop_times.txt": csv_text("trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type", times),
        "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\nS,1,1,1,1,1,0,0,20260101,20261231\n",
        "calendar_dates.txt": "service_id,date,exception_type\nS,20261114,1\nS,20261116,2\n",
    }


@pytest.fixture
def setup_feed(tmp_path):
    def setup(skm=None, ztm=None):
        database = tmp_path / "transit.db"
        for operator, content in (("skm", skm or files("skm")), ("ztm", ztm or files("ztm"))):
            archive = tmp_path / f"{operator}.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
                for name, text in content.items():
                    output.writestr(name, text)
            import_feed(operator, archive, database)
        return database
    return setup


@pytest.fixture
def api(tmp_path, setup_feed):
    with TestClient(create_app(tmp_path / "scenarios.db", setup_feed())) as client:
        yield client


@pytest.mark.parametrize("delay,margin,status,plan_b", [(0, 6, "Zdążysz", None), (6, 0, "Na styk", None),
                                                       (8, -2, "Nie zdążysz", "ztm:b"), (180, -174, "Nie zdążysz", None)])
def test_reference_transfer_reuses_engine_and_real_same_variant_plan_b(api, monkeypatch, delay, margin, status, plan_b):
    calls = []
    original = transfer_search.evaluate_transfer
    def spy(*args):
        calls.append(args)
        return original(*args)
    monkeypatch.setattr(transfer_search, "evaluate_transfer", spy)
    response = api.post(PATH, json={**REQUEST, "delay_minutes": delay})
    assert response.status_code == 200, response.text
    data = response.json()
    result = data["results"][0]
    assert result["evaluation"]["margin_minutes"] == margin
    assert result["evaluation"]["delay_threshold_minutes"] == 6
    assert result["evaluation"]["status"] == status
    assert (result["plan_b"]["trip_id"] if result["plan_b"] else None) == plan_b
    assert result["evaluation"]["plan_b_status"] == ("not_needed" if margin >= 0 else "available" if plan_b else "unavailable")
    assert len(calls) == 1
    assert data["arrival"]["arrival_at"] == "2026-11-12T17:42:00+01:00"  # Not the 17:43 departure.
    assert data["link"]["walking_time_source"] == "estimated"
    assert data["is_realtime"] is False and data["schedule_status"] == "planned"
    assert {source["operator"] for source in data["sources"]} == {"ztm", "skm"}
    assert all(source["sha256"] for source in data["sources"])


def test_links_keep_concrete_stops_and_do_not_expand_parent_station(api):
    response = api.get("/api/transit/transfer-links")
    assert response.status_code == 200
    link = response.json()["links"][0]
    assert link["arrival_stop_id"] == "skm:7500"
    assert link["departure_stop_id"] == "ztm:2001"
    assert link["arrival_stop"]["parent_station"] == "skm:H"
    assert link["walking_minutes"] is None
    assert link["walking_time_basis"] == "user_input"


@pytest.mark.parametrize("day,expected", [("2026-11-13", 200), ("2026-11-14", 200), ("2026-11-15", 422), ("2026-11-16", 422)])
def test_arriving_calendar_weekend_and_exceptions(api, day, expected):
    response = api.post(PATH, json={**REQUEST, "arrival_service_date": day})
    assert response.status_code == expected
    if expected == 422:
        assert response.json()["detail"]["code"] == "arrival_not_running"


def test_departure_calendar_dates_only_and_empty_service_day(tmp_path, setup_feed):
    ztm = files("ztm")
    del ztm["calendar.txt"]
    ztm["calendar_dates.txt"] = "service_id,date,exception_type\nS,20261112,1\nS,20261114,1\n"
    with TestClient(create_app(tmp_path / "user.db", setup_feed(ztm=ztm))) as client:
        assert client.post(PATH, json=REQUEST).json()["results"]
        response = client.post(PATH, json={**REQUEST, "arrival_service_date": "2026-11-13"})
        assert response.status_code == 200
        assert response.json()["outcome"] == "no_departures"
        assert response.json()["results"] == []


@pytest.mark.parametrize("arrival,departure,next_departure,day,expected_arrival,expected_departure", [
    ("23:58:00", "24:07:00", "25:03:00", "2026-11-12", "2026-11-12T23:58:00+01:00", "2026-11-13T00:07:00+01:00"),
    ("02:58:00", "03:07:00", "03:19:00", "2026-03-29", "2026-03-29T01:58:00+01:00", "2026-03-29T03:07:00+02:00"),
    ("01:58:00", "02:07:00", "02:19:00", "2026-10-25", "2026-10-25T02:58:00+02:00", "2026-10-25T02:07:00+01:00"),
])
def test_midnight_extended_gtfs_hours_and_dst(tmp_path, setup_feed, arrival, departure, next_departure, day, expected_arrival, expected_departure):
    skm, ztm = files("skm", arrival=arrival), files("ztm", departures_at=(departure, next_departure))
    for content in (skm, ztm):
        content["calendar.txt"] = content["calendar.txt"].replace("1,1,1,1,1,0,0", "1,1,1,1,1,1,1")
    with TestClient(create_app(tmp_path / "user.db", setup_feed(skm, ztm))) as client:
        response = client.post(PATH, json={**REQUEST, "arrival_service_date": day, "delay_minutes": 8})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["arrival"]["arrival_at"] == expected_arrival
        assert data["results"][0]["departure"]["departure_at"] == expected_departure
        assert data["results"][0]["departure"]["service_date"] == day
        assert data["results"][0]["evaluation"]["margin_minutes"] == -2
        assert data["results"][0]["plan_b"]["trip_id"] == "ztm:b"


def test_next_civil_day_and_previous_skm_service_date(tmp_path, setup_feed):
    skm = files("skm", arrival="24:42:00")
    ztm = files("ztm", departures_at=("00:51:00", "01:03:00"))
    database = setup_feed(skm, ztm)
    with TestClient(create_app(tmp_path / "user.db", database)) as client:
        data = client.post(PATH, json=REQUEST).json()
        assert data["arrival"]["arrival_at"] == "2026-11-13T00:42:00+01:00"
        assert data["results"][0]["departure"]["service_date"] == "2026-11-13"
        assert data["results"][0]["evaluation"]["margin_minutes"] == 6
        civil = departures(database, "ztm:2001", date(2026, 11, 13), 10)
        assert data["results"][0]["departure"] in civil["departures"]


@pytest.mark.parametrize("kind", ["direction", "downstream", "headsign", "route", "platform", "pickup"])
def test_variants_are_never_matched_by_name(tmp_path, setup_feed, kind):
    ztm = files("ztm")
    if kind == "direction":
        ztm["trips.txt"] = ztm["trips.txt"].replace("8,S,b,Oliwa,0", "8,S,b,Oliwa,1")
    elif kind == "downstream":
        ztm["stop_times.txt"] = ztm["stop_times.txt"].replace("b,18:08:00,18:08:00,9,", "b,18:08:00,18:08:00,10,")
    elif kind == "headsign":
        ztm["trips.txt"] = ztm["trips.txt"].replace("8,S,b,Oliwa,0", "8,S,b,Other,0")
    elif kind == "route":
        ztm["trips.txt"] = ztm["trips.txt"].replace("8,S,b,Oliwa,0", "other,S,b,Oliwa,0")
    elif kind == "platform":
        ztm["stop_times.txt"] = ztm["stop_times.txt"].replace("b,18:03:00,18:03:00,2001,", "b,18:03:00,18:03:00,2002,")
    else:
        ztm["stop_times.txt"] = ztm["stop_times.txt"].replace("b,18:03:00,18:03:00,2001,1,0,0", "b,18:03:00,18:03:00,2001,1,2,0")
    with TestClient(create_app(tmp_path / "user.db", setup_feed(ztm=ztm))) as client:
        response = client.post(PATH, json={**REQUEST, "delay_minutes": 8})
        if kind in ("direction", "downstream", "headsign"):
            assert response.status_code == 409
            assert response.json()["detail"]["code"] == "ambiguous_departure_variant"
            assert len(response.json()["detail"]["choices"]) == 2
        selected = client.post(PATH, json={**REQUEST, "departure_trip_id": "ztm:a", "delay_minutes": 8})
        assert selected.status_code == 200, selected.text
        assert selected.json()["results"][0]["plan_b"]["trip_id"] == "ztm:c"


@pytest.mark.parametrize("operator,change,code,status", [
    ("skm", "missing", "link_unavailable", 409), ("ztm", "station", "link_unavailable", 409),
    ("skm", "missing_time", "arrival_not_usable", 422), ("skm", "drop_off", "arrival_not_usable", 422),
    ("skm", "repeat", "ambiguous_arrival", 409),
])
def test_link_platform_and_arrival_rejections(tmp_path, setup_feed, operator, change, code, status):
    skm, ztm = files("skm"), files("ztm")
    content = skm if operator == "skm" else ztm
    if change == "missing":
        content["stops.txt"] = content["stops.txt"].replace("7500", "old7500")
        content["stop_times.txt"] = content["stop_times.txt"].replace("7500", "old7500")
    if change == "station":
        content["stops.txt"] = content["stops.txt"].replace("2001,Dworzec Główny 01,54,18,0,H", "2001,Dworzec Główny 01,54,18,1,")
    if change == "missing_time": content["stop_times.txt"] = content["stop_times.txt"].replace("a,17:42:00,", "a,,")
    if change == "drop_off": content["stop_times.txt"] = content["stop_times.txt"].replace("7500,2,0,0", "7500,2,0,1")
    if change == "repeat": content["stop_times.txt"] += "a,17:50:00,17:51:00,7500,3,0,0\n"
    with TestClient(create_app(tmp_path / "user.db", setup_feed(skm, ztm))) as client:
        response = client.post(PATH, json=REQUEST)
        assert response.status_code == status, response.text
        assert response.json()["detail"]["code"] == code
        if change == "repeat":
            assert client.post(PATH, json={**REQUEST, "arrival_stop_sequence": 2}).status_code == 200


@pytest.mark.parametrize("updates,status,code", [
    ({"link_id": "unknown"}, 404, "link_not_found"),
    ({"arrival_trip_id": "skm:unknown"}, 404, "arrival_not_found"),
    ({"departure_route_id": "ztm:unknown"}, 404, "route_not_found"),
    ({"departure_trip_id": "ztm:unknown"}, 409, "ambiguous_reference"),
    ({"arrival_service_date": "2027-01-01"}, 422, "feed_out_of_range"),
    ({"arrival_service_date": "2025-12-31"}, 422, "feed_out_of_range"),
])
def test_missing_and_out_of_range_data(api, updates, status, code):
    response = api.post(PATH, json={**REQUEST, **updates})
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code


@pytest.mark.parametrize("updates", [
    {"walking_minutes": -1}, {"walking_minutes": True}, {"walking_minutes": 181}, {"walking_minutes": None},
    {"delay_minutes": -1}, {"delay_minutes": "NaN"}, {"delay_minutes": 181}, {"delay_minutes": True},
    {"window_minutes": 361}, {"window_minutes": 0}, {"limit": 11}, {"limit": 0},
    {"arrival_service_date": "2026-02-30"}, {"arrival_service_date": 1794438000},
    {"arrival_trip_id": "ztm:a"}, {"departure_route_id": "skm:8"}, {"walking_time_source": "verified"},
])
def test_request_validation(api, updates):
    assert api.post(PATH, json={**REQUEST, **updates}).status_code == 422


def test_walking_time_required_and_no_network_or_writes(api, monkeypatch):
    request = {key: value for key, value in REQUEST.items() if key != "walking_minutes"}
    assert api.post(PATH, json=request).status_code == 422
    database = api.app.state.transit_database_path
    before = database.read_bytes()
    saved = api.get("/api/scenarios").json()
    from app.gtfs import archive
    def forbidden(*args, **kwargs): raise AssertionError("No network permitted")
    monkeypatch.setattr(archive, "urlopen", forbidden)
    assert api.post(PATH, json=REQUEST).status_code == 200
    assert database.read_bytes() == before
    assert api.get("/api/scenarios").json() == saved


def test_limits_do_not_silently_hide_departures(api, monkeypatch):
    monkeypatch.setattr(transfer_search, "MAX_CANDIDATES", 1)
    response = api.post(PATH, json=REQUEST)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "too_many_departures"


def test_missing_database_returns_503(tmp_path):
    database = tmp_path / "missing.db"
    with TestClient(create_app(tmp_path / "user.db", database)) as client:
        assert client.get("/api/transit/transfer-links").status_code == 503
        assert client.post(PATH, json=REQUEST).status_code == 503
    assert not database.exists()


def test_search_window_outside_departing_feed_is_not_empty_success(tmp_path, setup_feed):
    ztm = files("ztm")
    ztm["calendar.txt"] = ztm["calendar.txt"].replace("20261231", "20261111")
    ztm["calendar_dates.txt"] = "service_id,date,exception_type\nS,20261111,1\n"
    with TestClient(create_app(tmp_path / "user.db", setup_feed(ztm=ztm))) as client:
        response = client.post(PATH, json=REQUEST)
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "feed_out_of_range"
        assert response.json()["detail"]["operator"] == "ztm"


def test_no_plan_b_and_half_open_window(api):
    response = api.post(PATH, json={**REQUEST, "window_minutes": 21, "delay_minutes": 8})
    assert response.status_code == 200
    item = response.json()["results"][0]
    assert item["evaluation"]["plan_b_status"] == "unavailable"
    assert item["plan_b"] is None  # 18:03 is exactly the excluded end of this window.
    assert "oknie" in response.json()["limitations"][-1]


def test_duplicate_plan_b_instants_return_explanation_not_arbitrary_trip(tmp_path, setup_feed):
    ztm = files("ztm", departures_at=("17:51:00", "18:03:00", "18:03:00"))
    with TestClient(create_app(tmp_path / "user.db", setup_feed(ztm=ztm))) as client:
        response = client.post(PATH, json={**REQUEST, "delay_minutes": 8})
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "ambiguous_plan_b"
        assert {item["trip_id"] for item in response.json()["detail"]["choices"]} == {"ztm:b", "ztm:c"}


def test_search_rejects_window_crossing_end_of_feed(tmp_path, setup_feed):
    skm, ztm = files("skm", arrival="23:58:00"), files("ztm", departures_at=("24:07:00",))
    for content in (skm, ztm):
        content["calendar.txt"] = content["calendar.txt"].replace("20261231", "20261112")
        content["calendar_dates.txt"] = "service_id,date,exception_type\nS,20261112,1\n"
    with TestClient(create_app(tmp_path / "user.db", setup_feed(skm, ztm))) as client:
        response = client.post(PATH, json=REQUEST)
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "feed_out_of_range"


@pytest.mark.parametrize("day", ["0001-01-01", "9999-12-31"])
def test_extreme_civil_dates_do_not_regress_existing_departure_api(api, day):
    response = api.get("/api/transit/departures", params={"stop_id": "ztm:2001", "date": day})
    assert response.status_code == 200
    assert response.json()["departures"] == []


def test_pattern_limit_rejects_instead_of_truncating(api, monkeypatch):
    monkeypatch.setattr(transfer_search, "MAX_PATTERN_STOPS", 1)
    response = api.post(PATH, json=REQUEST)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "pattern_too_large"


def test_selected_departure_is_exact_course_not_first_in_variant(api):
    response = api.post(PATH, json={**REQUEST, "departure_trip_id": "ztm:b", "departure_service_date": "2026-11-12",
                                    "departure_stop_sequence": 1, "delay_minutes": 20})
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["departure"]["trip_id"] == "ztm:b"
    assert result["evaluation"]["margin_minutes"] == -2
    assert result["plan_b"]["trip_id"] == "ztm:c"
    assert response.json()["has_more"] is False


@pytest.mark.parametrize("updates,status", [
    ({"departure_service_date": "2026-11-12"}, 422),
    ({"departure_stop_sequence": 1}, 422),
    ({"departure_trip_id": "ztm:b", "departure_service_date": "2026-11-13"}, 422),
    ({"departure_trip_id": "ztm:b", "departure_service_date": "2026-11-12", "departure_stop_sequence": 2}, 409),
    ({"departure_trip_id": "ztm:b", "departure_service_date": 1794438000}, 422),
])
def test_exact_departure_validation(api, updates, status):
    assert api.post(PATH, json={**REQUEST, **updates}).status_code == status


@pytest.mark.parametrize("leg,stop,instant", [("arrival", "skm:7500", "2026-11-12T17:42:00+01:00"),
                                           ("departure", "ztm:2001", "2026-11-12T17:51:00+01:00")])
def test_picker_journeys_are_real_events_for_the_fixed_link(api, leg, stop, instant):
    database = api.app.state.transit_database_path
    before = database.read_bytes()
    response = api.get("/api/transit/journeys", params={"leg": leg, "date": "2026-11-12", "limit": 1})
    assert response.status_code == 200
    data = response.json()
    assert data["is_realtime"] is False and data["realtime_delay"] is None
    assert data["journeys"][0][f"{leg}_at"] == instant
    assert data["journeys"][0]["stop_id"] == stop
    assert data["journeys"][0]["service_date"] == "2026-11-12"
    assert data["journeys"][0]["route_type"] in (2, 3)
    assert data["has_more"] is (leg == "departure")
    assert database.read_bytes() == before


@pytest.mark.parametrize("query", [
    {"leg": "unknown", "date": "2026-11-12"}, {"leg": "arrival", "date": "2026-02-30"},
    {"leg": "arrival", "date": "2027-01-01"}, {"leg": "arrival", "date": "2026-11-12", "limit": 2001},
    {"leg": "arrival", "date": "2026-11-12", "limit": 0},
])
def test_picker_query_validation(api, query):
    assert api.get("/api/transit/journeys", params=query).status_code == 422


def test_arrival_picker_keeps_gtfs_service_day_after_midnight(tmp_path, setup_feed):
    database = setup_feed(skm=files("skm", arrival="24:42:00"))
    with TestClient(create_app(tmp_path / "user.db", database)) as client:
        response = client.get("/api/transit/journeys", params={"leg": "arrival", "date": "2026-11-13"})
        assert response.status_code == 200
        item = response.json()["journeys"][0]
        assert item["service_date"] == "2026-11-12"
        assert item["arrival_at"] == "2026-11-13T00:42:00+01:00"
        assert item["gtfs_arrival_time"] == "24:42:00"


def test_missing_departure_time_does_not_hide_a_known_arrival(tmp_path, setup_feed):
    skm = files("skm")
    skm["stop_times.txt"] = skm["stop_times.txt"].replace("a,17:42:00,17:43:00,", "a,17:42:00,,")
    with TestClient(create_app(tmp_path / "user.db", setup_feed(skm=skm))) as client:
        data = client.get("/api/transit/journeys", params={"leg": "arrival", "date": "2026-11-12"}).json()
        assert data["journeys"][0]["arrival_at"] == "2026-11-12T17:42:00+01:00"
        assert data["journeys"][0]["departure_at"] is None


@pytest.mark.parametrize("day,expected", [("2026-03-29", "2026-03-29T01:58:00+01:00"),
                                        ("2026-10-25", "2026-10-25T02:58:00+01:00")])
def test_arrival_picker_dst_uses_same_gtfs_semantics(tmp_path, setup_feed, day, expected):
    skm = files("skm", arrival="02:58:00")
    skm["calendar.txt"] = skm["calendar.txt"].replace("1,1,1,1,1,0,0", "1,1,1,1,1,1,1")
    with TestClient(create_app(tmp_path / "user.db", setup_feed(skm=skm))) as client:
        response = client.get("/api/transit/journeys", params={"leg": "arrival", "date": day})
        assert response.status_code == 200
        assert response.json()["journeys"][0]["arrival_at"] == expected


def test_departure_picker_respects_arriving_context(api):
    response = api.get("/api/transit/journeys", params={"leg": "departure", "date": "2026-11-12", "after": "2026-11-12T17:55:00+01:00"})
    assert response.status_code == 200
    assert [item["trip_id"] for item in response.json()["journeys"]] == ["ztm:b", "ztm:c"]
    response = api.get("/api/transit/journeys", params={"leg": "departure", "date": "2026-11-13", "after": "2026-11-12T17:55:00+01:00"})
    assert response.status_code == 200 and response.json()["journeys"] == []


@pytest.mark.parametrize("leg,after", [("arrival", "2026-11-12T17:55:00+01:00"), ("departure", "2026-03-29T02:30:00+01:00"),
                                     ("departure", "2026-11-12T17:55:00"), ("departure", "2026-11-12T17:55:00+02:00"),
                                     ("departure", "9999-12-31T23:59:00+01:00"), ("departure", "2027-01-01T01:00:00+01:00")])
def test_picker_context_validation(api, leg, after):
    assert api.get("/api/transit/journeys", params={"leg": leg, "date": "2026-11-12", "after": after}).status_code == 422
