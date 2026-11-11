import io
import json
import socket
import sqlite3
import stat
import struct
import warnings
import zipfile
from datetime import date
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest
from fastapi.testclient import TestClient

from app.gtfs import archive as archive_module
from app.gtfs.__main__ import main
from app.gtfs.archive import archive_manifest, download_feed
from app.gtfs.importer import import_feed, integer
from app.gtfs.schedule import gtfs_seconds, service_datetime
from app.gtfs.sources import GTFSError, SOURCES
from app.gtfs.store import departures, read_connection, search_stops, sources
from app.main import create_app


def fixture_files():
    return {
        "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\nA,Test,https://example.invalid,Europe/Warsaw\n",
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\n1,Gdańsk Główny,54.35,18.64\n2,Oliwa,54.40,18.57\n",
        "routes.txt": "route_id,agency_id,route_short_name,route_long_name,route_type\n1,A,8,,3\n",
        "trips.txt": "route_id,service_id,trip_id,trip_headsign,direction_id,block_id,shape_id\n1,S,1,Oliwa,0,1,1\n",
        "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n1,23:55:00,23:55:00,1,0\n1,24:10:00,24:10:00,2,1\n",
        "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\nS,1,1,1,1,1,0,0,20261101,20261231\n",
        "calendar_dates.txt": "service_id,date,exception_type\nS,20261111,2\nS,20261114,1\n",
    }


def write_zip(path: Path, files: dict[str, str], bom=False) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content.encode("utf-8-sig" if bom else "utf-8"))
    return path


@pytest.fixture
def feed(tmp_path):
    return write_zip(tmp_path / "fixture.zip", fixture_files())


@pytest.fixture
def transit_database(tmp_path, feed):
    path = tmp_path / "transit.db"
    import_feed("ztm", feed, path)
    return path


def test_utf8_bom_and_namespaces_do_not_collide(tmp_path):
    feed = write_zip(tmp_path / "bom.zip", fixture_files(), bom=True)
    database = tmp_path / "transit.db"
    for operator in ("ztm", "skm"):
        metadata = import_feed(operator, feed, database)
        assert metadata["row_counts"]["stop_times.txt"] == 2
        assert metadata["production_date"] is None
        assert metadata["downloaded_at"] is None
    stops = search_stops(database, "gdansk", 100)
    assert {stop["stop_id"] for stop in stops} == {"ztm:1", "skm:1"}
    assert all(stop["stop_name"] == "Gdańsk Główny" for stop in stops)
    with read_connection(database) as connection:
        for table in ("gtfs_agencies", "gtfs_routes", "gtfs_trips", "gtfs_services"):
            assert {row[0].split(":")[0] for row in connection.execute(f"SELECT id FROM {table}")} == {"ztm", "skm"}
        assert connection.execute("SELECT block_id,shape_id FROM gtfs_trips WHERE id='ztm:1'").fetchone()[:] == ("ztm:1", "ztm:1")


@pytest.mark.parametrize("day,expected", [("2026-11-13", 1), ("2026-11-14", 1), ("2026-11-15", 0), ("2026-11-11", 0)])
def test_weekdays_weekends_and_calendar_overrides(transit_database, day, expected):
    result = departures(transit_database, "ztm:1", date.fromisoformat(day), 50)
    assert len(result["departures"]) == expected


def test_calendar_dates_only(tmp_path):
    files = fixture_files()
    del files["calendar.txt"]
    files["calendar_dates.txt"] = "service_id,date,exception_type\nS,20261111,1\n"
    database = tmp_path / "dates-only.db"
    metadata = import_feed("ztm", write_zip(tmp_path / "feed.zip", files), database)
    assert metadata["service_start_date"] == metadata["service_end_date"] == "2026-11-11"
    assert len(departures(database, "ztm:1", date(2026, 11, 11), 50)["departures"]) == 1
    assert departures(database, "ztm:1", date(2026, 11, 12), 50)["departures"] == []


def test_calendar_without_exceptions(tmp_path):
    files = fixture_files()
    del files["calendar_dates.txt"]
    database = tmp_path / "calendar-only.db"
    import_feed("skm", write_zip(tmp_path / "feed.zip", files), database)
    assert len(departures(database, "skm:1", date(2026, 11, 11), 50)["departures"]) == 1


@pytest.mark.parametrize("hour,local", [("24", "00"), ("25", "01"), ("29", "05")])
def test_24_plus_times_query_the_civil_day_not_service_day(tmp_path, hour, local):
    files = fixture_files()
    files["stop_times.txt"] = files["stop_times.txt"].replace("24:10:00", f"{hour}:10:00")
    database = tmp_path / "transit.db"
    import_feed("ztm", write_zip(tmp_path / "feed.zip", files), database)
    result = departures(database, "ztm:2", date(2026, 11, 10), 50)
    assert result["departures"][0]["service_date"] == "2026-11-09"
    assert result["departures"][0]["departure_at"] == f"2026-11-10T{local}:10:00+01:00"
    assert result["departures"][0]["gtfs_departure_time"] == f"{hour}:10:00"


@pytest.mark.parametrize("day,seconds,expected", [
    (date(2026, 3, 29), 30 * 60, "2026-03-28T23:30:00+01:00"),
    (date(2026, 3, 29), 3 * 3600 + 30 * 60, "2026-03-29T03:30:00+02:00"),
    (date(2026, 10, 25), 3600 + 30 * 60, "2026-10-25T02:30:00+02:00"),
    (date(2026, 10, 25), 2 * 3600 + 30 * 60, "2026-10-25T02:30:00+01:00"),
    (date(2026, 10, 25), 25 * 3600, "2026-10-26T01:00:00+01:00"),
])
def test_gtfs_noon_minus_twelve_hour_dst_semantics(day, seconds, expected):
    assert service_datetime(day, seconds).isoformat() == expected


def test_departures_include_next_service_day_at_spring_boundary(tmp_path):
    files = fixture_files()
    del files["calendar.txt"]
    files["calendar_dates.txt"] = "service_id,date,exception_type\nS,20260329,1\n"
    files["stop_times.txt"] = files["stop_times.txt"].replace("23:55:00", "00:30:00")
    database = tmp_path / "transit.db"
    import_feed("ztm", write_zip(tmp_path / "feed.zip", files), database)
    result = departures(database, "ztm:1", date(2026, 3, 28), 50)
    assert result["departures"][0]["departure_at"] == "2026-03-28T23:30:00+01:00"
    assert result["departures"][0]["service_date"] == "2026-03-29"
    assert departures(database, "ztm:1", date(2026, 3, 29), 50)["departures"] == []


def test_fall_back_returns_two_equal_wall_times_in_instant_order(tmp_path):
    files = fixture_files()
    del files["calendar.txt"]
    files["calendar_dates.txt"] = "service_id,date,exception_type\nS,20261025,1\n"
    files["trips.txt"] += "1,S,2,Oliwa,0,2,2\n"
    files["stop_times.txt"] = "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n1,01:30:00,01:30:00,1,0\n2,02:30:00,02:30:00,1,0\n"
    database = tmp_path / "transit.db"
    import_feed("ztm", write_zip(tmp_path / "feed.zip", files), database)
    result = departures(database, "ztm:1", date(2026, 10, 25), 50)
    assert [row["departure_at"] for row in result["departures"]] == ["2026-10-25T02:30:00+02:00", "2026-10-25T02:30:00+01:00"]
    assert departures(database, "ztm:1", date(2026, 10, 25), 1)["has_more"] is True


@pytest.mark.parametrize("value", ["25:61:00", "-1:00:00", "24:00", "168:00:00", "12:00:99"])
def test_invalid_gtfs_times(value):
    with pytest.raises(GTFSError):
        gtfs_seconds(value)


@pytest.mark.parametrize("change", [
    {"calendar.txt": None, "calendar_dates.txt": None},
    {"agency.txt": "agency_id,agency_name,agency_url,agency_timezone\nA,Test,https://example.invalid,UTC\n"},
    {"stops.txt": "stop_id,stop_name,stop_lat,stop_lon\n1,Test,nan,18\n"},
    {"routes.txt": "route_id,agency_id,route_short_name,route_type\n1,missing,8,3\n"},
    {"stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n1,12:00:00,12:00:00,missing,0\n"},
    {"stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n1,12:01:00,12:00:00,1,0\n"},
    {"stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n1,12:00:00,12:00:00,1,0\n1,11:00:00,11:00:00,2,1\n"},
    {"stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n1,12:00:00,12:00:00,1,0\n1,,,2,1\n1,11:00:00,11:00:00,2,2\n"},
    {"frequencies.txt": "trip_id,start_time,end_time,headway_secs\n1,08:00:00,10:00:00,600\n"},
    {"stops.txt": "stop_id,stop_id,stop_lat,stop_lon\n1,Test,54,18\n"},
    {"calendar_dates.txt": "service_id,date,exception_type\nS,20260230,1\n"},
    {"calendar_dates.txt": "service_id,date,exception_type\nS,20261111,3\n"},
    {"stops.txt": "stop_id,stop_name,stop_lat,stop_lon\n1,Test,54,18,extra\n"},
])
def test_invalid_feed_rolls_back_without_touching_other_source(tmp_path, transit_database, feed, change):
    import_feed("skm", feed, transit_database)
    before = sources(transit_database)
    files = fixture_files()
    for name, value in change.items():
        if value is None:
            files.pop(name, None)
        else:
            files[name] = value
    with pytest.raises(GTFSError):
        import_feed("ztm", write_zip(tmp_path / "bad.zip", files), transit_database)
    assert sources(transit_database) == before
    assert len(search_stops(transit_database, "", 100)) == 4


def test_reimport_is_idempotent_and_other_operator_survives(transit_database, feed):
    import_feed("skm", feed, transit_database)
    import_feed("ztm", feed, transit_database)
    with read_connection(transit_database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM gtfs_stop_times").fetchone()[0] == 4


def test_import_refuses_user_scenario_database(tmp_path, feed):
    path = tmp_path / "scenarios.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE scenario(id INTEGER PRIMARY KEY,name TEXT)")
        connection.execute("INSERT INTO scenario VALUES (1,'keep')")
    before = path.read_bytes()
    with pytest.raises(GTFSError, match="Odmowa zapisu"):
        import_feed("ztm", feed, path)
    assert path.read_bytes() == before


def test_non_sqlite_target_is_preserved_and_cli_reports_error(tmp_path, feed, capsys):
    path = tmp_path / "not-sqlite.db"
    path.write_bytes(b"keep this existing file")
    assert main(["ztm", "--archive", str(feed), "--database", str(path)]) == 1
    assert "baza GTFS" in capsys.readouterr().err
    assert path.read_bytes() == b"keep this existing file"


@pytest.mark.parametrize("kind", ["corrupt", "traversal", "symlink", "duplicate", "missing", "ratio", "utf8", "filename"])
def test_invalid_archives(tmp_path, kind):
    files = fixture_files()
    path = tmp_path / "bad.zip"
    if kind == "corrupt":
        path.write_bytes(b"not a ZIP")
    else:
        if kind == "missing": del files["stops.txt"]
        if kind == "traversal": files["../outside.txt"] = "unsafe"
        if kind == "ratio": files["bomb.txt"] = "0" * 100000
        write_zip(path, files)
        with zipfile.ZipFile(path, "a") as archive:
            if kind == "symlink":
                info = zipfile.ZipInfo("link.txt")
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, "outside")
            if kind == "duplicate":
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    archive.writestr("stops.txt", files["stops.txt"])
            if kind == "utf8":
                archive.writestr("attributions.txt", b"header\n\xff")
        if kind == "filename":
            content = bytearray(path.read_bytes())
            local, central = content.index(b"PK\x03\x04"), content.index(b"PK\x01\x02")
            for header, flags_offset, name_offset in [(local, 6, 30), (central, 8, 46)]:
                flags = struct.unpack_from("<H", content, header + flags_offset)[0]
                struct.pack_into("<H", content, header + flags_offset, flags | 0x800)
                content[header + name_offset] = 0xFF
            path.write_bytes(content)
    with pytest.raises(GTFSError):
        import_feed("ztm", path, tmp_path / "transit.db")
    assert not (tmp_path.parent / "outside.txt").exists()


def test_expanded_size_limit(tmp_path, feed, monkeypatch):
    monkeypatch.setattr(archive_module, "MAX_EXPANDED_BYTES", 1)
    with pytest.raises(GTFSError, match="512 MiB"):
        archive_manifest(feed)


@pytest.mark.parametrize("field,value", [("count", 1000), ("directory", 2 * 1024 * 1024)])
def test_zip_directory_limits_are_checked_before_opening_members(tmp_path, feed, field, value):
    content = bytearray(feed.read_bytes())
    offset = content.rfind(b"PK\x05\x06")
    if field == "count":
        struct.pack_into("<HH", content, offset + 8, value, value)
    else:
        struct.pack_into("<I", content, offset + 12, value)
    path = tmp_path / "directory.zip"
    path.write_bytes(content)
    with pytest.raises(GTFSError, match="katalog ZIP"):
        archive_manifest(path)


class FakeResponse(io.BytesIO):
    def __init__(self, data, length=None):
        super().__init__(data)
        self.headers = {"Last-Modified": "Wed, 11 Nov 2026 00:00:00 GMT", "ETag": "test"}
        if length is not None: self.headers["Content-Length"] = str(length)

    def geturl(self):
        return SOURCES["ztm"].feed_url


@pytest.mark.parametrize("error", [URLError("offline"), socket.timeout("timeout"), IncompleteRead(b"partial", 100), HTTPError("https://example.invalid", 503, "Unavailable", None, None)])
def test_network_errors_preserve_cached_file(tmp_path, monkeypatch, error):
    target = tmp_path / "ztm.zip"
    target.write_bytes(b"keep")
    def fail(*args, **kwargs): raise error
    monkeypatch.setattr(archive_module, "urlopen", fail)
    with pytest.raises(GTFSError, match="Nie udało się pobrać"):
        download_feed(SOURCES["ztm"], tmp_path)
    assert target.read_bytes() == b"keep"
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.parametrize("kind", ["header", "stream", "truncated", "zip"])
def test_download_limits_and_validation(tmp_path, monkeypatch, feed, kind):
    data = feed.read_bytes()
    length = len(data)
    if kind == "header": length = archive_module.MAX_DOWNLOAD_BYTES + 1
    if kind == "stream": monkeypatch.setattr(archive_module, "MAX_DOWNLOAD_BYTES", 100); length = None
    if kind == "truncated": length += 1
    if kind == "zip": data = b"broken"; length = len(data)
    monkeypatch.setattr(archive_module, "urlopen", lambda *args, **kwargs: FakeResponse(data, length))
    with pytest.raises(GTFSError):
        download_feed(SOURCES["ztm"], tmp_path)
    assert not (tmp_path / "ztm.zip").exists()
    assert not list(tmp_path.glob("*.part"))


def test_successful_download_and_local_cli(tmp_path, monkeypatch, feed, capsys):
    data = feed.read_bytes()
    monkeypatch.setattr(archive_module, "urlopen", lambda *args, **kwargs: FakeResponse(data, len(data)))
    path, provenance = download_feed(SOURCES["ztm"], tmp_path)
    assert provenance["import_method"] == "official_download"
    assert provenance["downloaded_at"]
    assert provenance["last_modified"]
    assert path.read_bytes() == data
    assert main(["ztm", "--archive", str(path), "--database", str(tmp_path / "cli.db")]) == 0
    assert json.loads(capsys.readouterr().out)["import_method"] == "local_archive"
    path.write_bytes(b"bad")
    assert main(["ztm", "--archive", str(path), "--database", str(tmp_path / "cli.db")]) == 1


def test_download_total_time_budget(tmp_path, monkeypatch, feed):
    data = feed.read_bytes()
    ticks = iter([0, 181])
    monkeypatch.setattr(archive_module.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(archive_module, "urlopen", lambda *args, **kwargs: FakeResponse(data, len(data)))
    with pytest.raises(GTFSError, match="180 sekund"):
        download_feed(SOURCES["ztm"], tmp_path)
    assert not list(tmp_path.glob("*.part"))


def test_cli_and_api_share_configured_database(tmp_path, monkeypatch, feed, capsys):
    database = tmp_path / "configured.db"
    monkeypatch.setenv("PRZESIADKA_TRANSIT_PATH", str(database))
    assert main(["ztm", "--archive", str(feed)]) == 0
    capsys.readouterr()
    with TestClient(create_app(tmp_path / "user.db")) as client:
        assert client.app.state.transit_database_path == database
        assert client.get("/api/transit/sources").json()["sources"][0]["imported"] is True


def test_optional_attribution_identifiers_are_namespaced(tmp_path):
    files = fixture_files()
    files["attributions.txt"] = "attribution_id,agency_id,route_id,trip_id,organization_name\n1,A,1,1,Test\n"
    metadata = import_feed("ztm", write_zip(tmp_path / "feed.zip", files), tmp_path / "transit.db")
    row = metadata["attributions"][0]
    assert row["attribution_id"] == row["route_id"] == row["trip_id"] == "ztm:1"
    assert row["agency_id"] == "ztm:A"


def test_csv_physical_line_is_bounded(tmp_path, feed, monkeypatch):
    monkeypatch.setattr(archive_module, "MAX_CSV_LINE_CHARS", 10)
    with pytest.raises(GTFSError, match="limit długości wiersza"):
        import_feed("ztm", feed, tmp_path / "transit.db")


def test_huge_integer_has_a_readable_error():
    with pytest.raises(GTFSError):
        integer("9" * 10000)


def test_startup_never_downloads_and_api_does_not_create_gtfs_database(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError("network called at startup")
    monkeypatch.setattr(archive_module, "urlopen", forbidden)
    transit = tmp_path / "missing.db"
    with TestClient(create_app(tmp_path / "user.db", transit)) as client:
        assert client.get("/api/health").status_code == 200
        assert all(not source["imported"] for source in client.get("/api/transit/sources").json()["sources"])
        assert client.get("/api/transit/stops").status_code == 503
    assert not transit.exists()


def test_transit_api_is_read_only_and_returns_real_fixture_metadata(tmp_path, transit_database):
    before = transit_database.read_bytes()
    with TestClient(create_app(tmp_path / "user.db", transit_database)) as client:
        response = client.get("/api/transit/sources")
        assert response.status_code == 200
        data = response.json()
        assert data["is_realtime"] is False
        assert data["sources"][0]["imported"] is True
        assert data["sources"][0]["sha256"]
        assert data["sources"][1]["imported"] is False
        response = client.get("/api/transit/stops", params={"query": "gdansk"})
        assert response.status_code == 200
        assert response.json()["stops"][0]["stop_id"] == "ztm:1"
        response = client.get("/api/transit/departures", params={"stop_id": "ztm:2", "date": "2026-11-10"})
        assert response.status_code == 200
        departure = response.json()["departures"][0]
        assert departure["line"] == "8"
        assert departure["direction"] == "Oliwa"
        assert departure["departure_at"] == "2026-11-10T00:10:00+01:00"
        assert client.get("/api/transit/departures", params={"stop_id": "ztm:missing", "date": "2026-11-10"}).status_code == 404
        assert client.post("/api/transit/stops").status_code == 405
        assert client.get("/api/transit/stops", params={"query": "%"}).json()["stops"] == []
    assert transit_database.read_bytes() == before


@pytest.mark.parametrize("query", [
    {"stop_id": "bad", "date": "2026-11-10"}, {"stop_id": "ztm:1", "date": "2026-02-30"},
    {"stop_id": "ztm:1", "date": "1794294000"}, {"stop_id": "ztm:1", "date": "2026-11-10", "limit": 0},
    {"stop_id": "ztm:1", "date": "2026-11-10", "limit": 201},
])
def test_transit_query_validation(tmp_path, transit_database, query):
    with TestClient(create_app(tmp_path / "user.db", transit_database)) as client:
        assert client.get("/api/transit/departures", params=query).status_code == 422


def test_missing_departure_is_not_interpolated_and_pickup_forbidden_is_hidden(tmp_path):
    files = fixture_files()
    files["stop_times.txt"] = "trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type\n1,23:55:00,,1,0,0\n1,24:10:00,24:10:00,2,1,1\n"
    database = tmp_path / "transit.db"
    metadata = import_feed("ztm", write_zip(tmp_path / "feed.zip", files), database)
    assert metadata["missing_departure_times"] == 1
    assert departures(database, "ztm:1", date(2026, 11, 10), 50)["departures"] == []
    assert departures(database, "ztm:2", date(2026, 11, 10), 50)["departures"] == []
