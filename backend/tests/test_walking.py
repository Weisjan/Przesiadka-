import io
import json
import socket
import sqlite3
import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.walking import client, store
from app.walking.__main__ import main
from app.walking.client import WalkingError
from gtfs_fixtures import setup_feed

PAIR = ("skm:7500", "ztm:2001")
POINTS = ((18.6443487, 54.3565922), (18.645663339105, 54.355509269859))
NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
AVAILABLE = {"status": "available", "distance_m": 321.4, "walking_seconds": 241.2}
NO_ROUTE = {"status": "no_route", "distance_m": None, "walking_seconds": None}
FIXTURE = Path(__file__).parent / "fixtures" / "ors_walking.json"


@pytest.fixture(autouse=True)
def offline_ors(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must never call the ORS network")
    monkeypatch.setattr(client, "open_request", forbidden)
    monkeypatch.setattr(client.time, "sleep", lambda _: None)
    monkeypatch.setenv("ORS_API_KEY", "test-only-key-not-a-real-secret")


def http_error(status, code=None):
    data = {"error": {"code": code, "message": "test-only-key-not-a-real-secret"}}
    return HTTPError(client.ENDPOINT, status, "provider response", {}, io.BytesIO(json.dumps(data).encode()))


def test_parse_synthetic_ors_fixture():
    assert client.parse_response(json.loads(FIXTURE.read_text())) == AVAILABLE


@pytest.mark.parametrize("fake_key", ["fictional-legacy-key", "eyJmaWtlIjoxfQ.eyJ0ZXN0Ijp0cnVlfQ.fake-signature",
                                     "eyJmaWtlIjoxfQ." + "a" * 5000 + ".fake-signature"])
def test_opaque_legacy_and_long_jwt_style_keys_are_forwarded_unchanged(monkeypatch, fake_key):
    monkeypatch.setenv("ORS_API_KEY", fake_key)
    def respond(request, **kwargs):
        assert request.get_header("Authorization") == fake_key
        return io.BytesIO(FIXTURE.read_bytes())
    monkeypatch.setattr(client, "open_request", respond)
    assert client.fetch_walking(*POINTS, max_requests=1) == AVAILABLE


@pytest.mark.parametrize("fake_key", ["fake key", "fake\r\nInjected: header", "fake\x00key", "fake\tkey", "fikcyjny-ą"])
def test_unsafe_header_characters_are_rejected_without_network_or_key_echo(monkeypatch, fake_key):
    monkeypatch.setattr(client.os, "environ", {"ORS_API_KEY": fake_key})
    with pytest.raises(WalkingError) as failure:
        client.fetch_walking(*POINTS, max_requests=1)
    assert failure.value.code == "invalid_key"
    assert fake_key not in str(failure.value)


def test_request_order_header_and_fixed_current_https_endpoint(monkeypatch):
    calls = []
    def respond(request, **kwargs):
        calls.append((request, kwargs))
        return io.BytesIO(FIXTURE.read_bytes())
    monkeypatch.setattr(client, "open_request", respond)
    assert client.fetch_walking(*POINTS) == AVAILABLE
    request, options = calls[0]
    assert request.full_url == "https://api.heigit.org/openrouteservice/v2/directions/foot-walking/json"
    assert request.get_header("Authorization") == "test-only-key-not-a-real-secret"
    assert "api_key" not in request.full_url
    assert json.loads(request.data) == {"coordinates": [list(point) for point in POINTS], "geometry": False, "instructions": False, "units": "m"}
    assert options["timeout"] == 10


@pytest.mark.parametrize("point", [(None, 54), (float("nan"), 54), (float("inf"), 54), (181, 54), (18, 91), (True, 54), ("18", 54)])
def test_invalid_coordinates_never_make_request(point):
    with pytest.raises(WalkingError, match="współrzędne"):
        client.fetch_walking(point, POINTS[1])


@pytest.mark.parametrize("status,code", [(401, "unauthorized"), (403, "forbidden"), (429, "rate_limited"), (501, "http_error")])
def test_auth_rate_limit_and_permanent_errors_are_not_retried(monkeypatch, status, code):
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise http_error(status)
    monkeypatch.setattr(client, "open_request", fail)
    with pytest.raises(WalkingError) as failure:
        client.fetch_walking(*POINTS, max_requests=3)
    assert failure.value.code == code
    assert len(calls) == 1
    assert "test-only-key-not-a-real-secret" not in str(failure.value)


@pytest.mark.parametrize("status", [408, 500, 502, 503, 504])
def test_transient_http_errors_retry_within_budget(monkeypatch, status):
    calls, sleeps = [], []
    def respond(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise http_error(status)
        return io.BytesIO(FIXTURE.read_bytes())
    monkeypatch.setattr(client, "open_request", respond)
    monkeypatch.setattr(client.time, "sleep", sleeps.append)
    assert client.fetch_walking(*POINTS, max_requests=2) == AVAILABLE
    assert len(calls) == 2 and sleeps == [1]


@pytest.mark.parametrize("error", [socket.timeout("do not print"), URLError("test-only-key-not-a-real-secret")])
def test_network_timeout_and_budget_are_sanitized(monkeypatch, error):
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise error
    monkeypatch.setattr(client, "open_request", fail)
    with pytest.raises(WalkingError) as failure:
        client.fetch_walking(*POINTS, max_requests=2)
    assert len(calls) == 2
    assert "test-only-key-not-a-real-secret" not in str(failure.value)


def test_retry_after_prevents_early_transient_error_retry(monkeypatch):
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise HTTPError(client.ENDPOINT, 503, "busy", {"Retry-After": "120"}, io.BytesIO())
    monkeypatch.setattr(client, "open_request", fail)
    with pytest.raises(WalkingError) as failure:
        client.fetch_walking(*POINTS, max_requests=3)
    assert len(calls) == 1 and failure.value.code == "retry_after"


def test_tls_errors_and_redirects_do_not_retry_or_forward_credentials(monkeypatch):
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise URLError(ssl.SSLCertVerificationError("certificate failed"))
    monkeypatch.setattr(client, "open_request", fail)
    with pytest.raises(WalkingError):
        client.fetch_walking(*POINTS)
    assert len(calls) == 1
    with pytest.raises(WalkingError, match="przekierował"):
        client.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.invalid")


@pytest.mark.parametrize("status,code", [(400, 2009), (404, 2009), (404, 2010)])
def test_explicit_no_route_errors_are_not_zero_minutes(monkeypatch, status, code):
    def fail(*args, **kwargs): raise http_error(status, code)
    monkeypatch.setattr(client, "open_request", fail)
    assert client.fetch_walking(*POINTS) == NO_ROUTE


@pytest.mark.parametrize("value", [None, {}, {"routes": None}, {"routes": [{}, {}]}, {"routes": [{}]},
                                 {"routes": [], "error": {"code": 401}}])
def test_invalid_response_shapes_are_rejected(value):
    with pytest.raises(WalkingError): client.parse_response(value)


@pytest.mark.parametrize("distance,duration", [(None, 5), (True, 5), ("10", 5), (float("nan"), 5), (1, float("inf")),
                                             (0, 0), (-1, 5), (1, 10801), (20001, 5)])
def test_invalid_summary_is_rejected(distance, duration):
    with pytest.raises(WalkingError):
        client.parse_response({"routes": [{"summary": {"distance": distance, "duration": duration}}]})


@pytest.mark.parametrize("body", [b"not JSON", b"\xff", b"x" * 65537])
def test_invalid_bounded_json_never_leaks_body(monkeypatch, body):
    monkeypatch.setattr(client, "open_request", lambda *a, **k: io.BytesIO(body))
    with pytest.raises(WalkingError): client.fetch_walking(*POINTS)


def test_directional_save_read_update_and_persistence(tmp_path):
    path = tmp_path / "walking.db"
    store.save_result(path, *PAIR, POINTS, AVAILABLE, NOW)
    saved = store.read_saved(path, *PAIR)
    assert saved["confidence"] == "estimated"
    assert saved["walking_seconds"] == 241.2 and saved["distance_m"] == 321.4
    assert saved["from_longitude"] == POINTS[0][0]
    assert saved["license"] == "CC-BY-SA-4.0" and "HeiGIT" in saved["attribution"]
    assert store.read_saved(path, *reversed(PAIR)) is None
    store.save_result(path, *reversed(PAIR), tuple(reversed(POINTS)), {**AVAILABLE, "walking_seconds": 300}, NOW)
    store.save_result(path, *PAIR, POINTS, {**AVAILABLE, "walking_seconds": 242}, NOW + timedelta(hours=1))
    assert store.read_saved(path, *PAIR)["walking_seconds"] == 242
    assert store.read_saved(path, *reversed(PAIR))["walking_seconds"] == 300
    with sqlite3.connect(path) as database:
        assert database.execute("SELECT COUNT(*) FROM walking_transfers").fetchone()[0] == 2


def test_cache_freshness_checks_coordinates_age_profile_and_clock(tmp_path):
    row = store.save_result(tmp_path / "walking.db", *PAIR, POINTS, AVAILABLE, NOW)
    assert store.freshness(row, POINTS, NOW + timedelta(days=29))
    assert not store.freshness(row, POINTS, NOW + timedelta(days=30))
    assert not store.freshness(row, POINTS, NOW - timedelta(seconds=1))
    assert not store.freshness(row, ((18.7, 54.3), POINTS[1]), NOW)
    assert not store.freshness({**row, "profile": "driving-car"}, POINTS, NOW)
    assert not store.freshness({**row, "license": "outdated"}, POINTS, NOW)


def test_negative_cache_has_shorter_lifetime_and_null_metrics(tmp_path):
    row = store.save_result(tmp_path / "walking.db", *PAIR, POINTS, NO_ROUTE, NOW)
    assert row["walking_seconds"] is None and row["distance_m"] is None
    assert store.freshness(row, POINTS, NOW + timedelta(hours=23))
    assert not store.freshness(row, POINTS, NOW + timedelta(days=1))


@pytest.mark.parametrize("kind", ["sqlite", "not_sqlite"])
def test_never_modify_user_database(tmp_path, kind):
    path = tmp_path / "user.db"
    if kind == "sqlite":
        with sqlite3.connect(path) as database:
            database.execute("CREATE TABLE scenario(id INTEGER PRIMARY KEY)")
    else: path.write_bytes(b"preserve this file")
    before = path.read_bytes()
    with pytest.raises(WalkingError): store.save_result(path, *PAIR, POINTS, AVAILABLE, NOW)
    assert path.read_bytes() == before


def test_cli_dry_run_missing_key_and_initial_pair_only(tmp_path, setup_feed, monkeypatch, capsys):
    transit = setup_feed()
    path = tmp_path / "walking.db"
    args = [*PAIR, "--transit-database", str(transit), "--database", str(path)]
    assert main([*args, "--dry-run"]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["coordinates"] == [[18, 54], [18, 54]]
    assert not path.exists()
    monkeypatch.delenv("ORS_API_KEY")
    assert main(args) == 1
    assert "ORS_API_KEY" in capsys.readouterr().err
    assert not path.exists()
    assert main([*reversed(PAIR), "--transit-database", str(transit), "--database", str(path)]) == 1
    assert "wyłącznie" in capsys.readouterr().err


def test_cli_cache_resume_refresh_and_preserve_previous_result_on_error(tmp_path, setup_feed, monkeypatch, capsys):
    transit, path = setup_feed(), tmp_path / "walking.db"
    calls = []
    def respond(*args, **kwargs):
        assert '"coordinates"' in capsys.readouterr().out  # Preview was printed before request.
        calls.append(1)
        return io.BytesIO(FIXTURE.read_bytes())
    monkeypatch.setattr(client, "open_request", respond)
    args = [*PAIR, "--transit-database", str(transit), "--database", str(path), "--max-requests", "1"]
    assert main(args) == 0 and len(calls) == 1
    capsys.readouterr()
    monkeypatch.delenv("ORS_API_KEY")
    assert main(args) == 0 and len(calls) == 1
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["action"] == "cached"
    before = path.read_bytes()
    assert main([*args, "--refresh"]) == 1
    assert "ORS_API_KEY" in capsys.readouterr().err
    assert path.read_bytes() == before


@pytest.mark.parametrize("limit", ["0", "4", "bad"])
def test_cli_request_budget_is_bounded(limit):
    with pytest.raises(SystemExit): main([*PAIR, "--max-requests", limit])


def test_read_only_endpoint_missing_available_stale_no_route_and_startup(tmp_path, setup_feed):
    transit, walking = setup_feed(), tmp_path / "walking.db"
    before = transit.read_bytes()
    with TestClient(create_app(transit, walking)) as api:
        query = {"from_stop_id": PAIR[0], "to_stop_id": PAIR[1]}
        assert not walking.exists()
        response = api.get("/api/transit/walking-transfers", params=query)
        assert response.status_code == 200 and response.json()["status"] == "missing"
        assert not walking.exists()
        points = store.stop_pair(transit, *PAIR)
        store.save_result(walking, *PAIR, points, AVAILABLE)
        data_before = walking.read_bytes()
        data = api.get("/api/transit/walking-transfers", params=query).json()
        assert data["status"] == "available"
        assert data["estimate"]["walking_minutes"] == 5 and data["estimate"]["walking_seconds"] == 241.2
        assert data["estimate"]["confidence"] == "estimated"
        assert walking.read_bytes() == data_before
        store.save_result(walking, *PAIR, points, AVAILABLE, datetime.now(timezone.utc) - timedelta(days=31))
        assert api.get("/api/transit/walking-transfers", params=query).json()["status"] == "stale"
        store.save_result(walking, *PAIR, points, NO_ROUTE)
        data = api.get("/api/transit/walking-transfers", params=query).json()
        assert data["status"] == "no_route" and data["estimate"]["walking_minutes"] is None
        assert api.get("/api/transit/walking-transfers", params={"from_stop_id": PAIR[1], "to_stop_id": PAIR[0]}).json()["status"] == "missing"
        assert api.get("/api/transit/walking-transfers", params={**query, "to_stop_id": "ztm:unknown"}).status_code == 404
        assert api.get("/api/transit/walking-transfers", params={**query, "to_stop_id": PAIR[0]}).status_code == 422
        assert api.get("/api/transit/walking-transfers", params={**query, "to_stop_id": "bad"}).status_code == 422
        assert api.post("/api/transit/walking-transfers", json=query).status_code == 405
    assert transit.read_bytes() == before


def test_cli_discards_provider_metadata_and_never_stores_or_prints_key(tmp_path, setup_feed, monkeypatch, capsys):
    response = json.loads(FIXTURE.read_text())
    response["metadata"] = {"query": {"api_key": "test-only-key-not-a-real-secret"}, "attribution": "test-only-key-not-a-real-secret"}
    monkeypatch.setattr(client, "open_request", lambda *a, **k: io.BytesIO(json.dumps(response).encode()))
    database = tmp_path / "walking.db"
    assert main([*PAIR, "--transit-database", str(setup_feed()), "--database", str(database)]) == 0
    output = capsys.readouterr()
    assert "test-only-key-not-a-real-secret" not in output.out + output.err
    assert b"test-only-key-not-a-real-secret" not in database.read_bytes()


@pytest.mark.parametrize("column,value", [("calculated_at", "bad-date"), ("calculated_at", "2026-11-12T12:00:00"), ("walking_seconds", None)])
def test_invalid_cache_rows_produce_readable_503_without_modifying_them(tmp_path, setup_feed, column, value):
    transit, path = setup_feed(), tmp_path / "walking.db"
    store.save_result(path, *PAIR, store.stop_pair(transit, *PAIR), AVAILABLE)
    with sqlite3.connect(path) as database:
        database.execute(f"UPDATE walking_transfers SET {column}=?", (value,))
    before = path.read_bytes()
    with TestClient(create_app(transit, path)) as api:
        response = api.get("/api/transit/walking-transfers", params={"from_stop_id": PAIR[0], "to_stop_id": PAIR[1]})
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "invalid_cache"
    assert path.read_bytes() == before
