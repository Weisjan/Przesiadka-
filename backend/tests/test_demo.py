import hashlib
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import demo
from app.gtfs import planner
from app.gtfs.transfer_search import LINK
from app.main import create_app
from app.walking import client as ors, store
from gtfs_fixtures import setup_feed


@pytest.fixture
def snapshot(tmp_path, setup_feed, monkeypatch):
    monkeypatch.setattr(ors, "open_request", lambda *a, **k: pytest.fail("Demo must remain offline"))
    monkeypatch.setattr(demo, "ORIGIN_NAME", "Earlier stop")
    monkeypatch.setattr(demo, "PROFILES", (("fixture", "Destination", "Synthetic fixture"),))
    monkeypatch.setattr(demo, "LINKS", {LINK.id: LINK})
    monkeypatch.setattr(planner, "LINKS", {LINK.id: LINK})
    transit = setup_feed()
    walking = tmp_path / "walking.db"
    store.save_result(walking, "skm:7500", "ztm:2001", store.stop_pair(transit, "skm:7500", "ztm:2001"),
                      {"status": "available", "walking_seconds": 153.7, "distance_m": 213.5}, now=datetime(2026, 11, 12, tzinfo=timezone.utc))
    directory = tmp_path / "demo"
    before = [p.read_bytes() for p in (transit, walking)]
    result = demo.prepare(transit, walking, directory)
    assert before == [p.read_bytes() for p in (transit, walking)]
    assert result["bytes"] > 0
    return directory, transit, walking


def body():
    return {"origin_stop_id": "skm:1", "destination_stop_id": "ztm:9", "departure_date": "2026-11-13", "departure_time": "17:00"}


def test_snapshot_runs_normal_planner_and_retains_source_records(snapshot):
    directory, transit, walking = snapshot
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()}
    with TestClient(demo.create_demo_app(directory)) as api:
        sources = api.get("/api/transit/sources").json()
        assert sources["demo"]["enabled"] is True
        assert sources["demo"]["examples"][0]["origin"]["stops"][0]["stop_id"] == "skm:1"
        response = api.post("/api/transit/journeys/plan", json=body())
        assert response.status_code == 200, response.text
        assert response.json()["demo"]["walking_reference_at"] == sources["demo"]["walking_reference_at"]
        item = response.json()["results"][0]
        assert item["evaluation"]["margin_minutes"] == 6
        assert item["link"]["walking"]["estimate"]["walking_seconds"] == 153.7
        assert item["link"]["walking"]["estimate"]["calculated_at"].startswith("2026-11-12")
        assert api.post("/api/transit/journeys/plan", json={**body(), "departure_time": "19:00"}).status_code == 422
        assert api.get("/api/transit/journeys?leg=arrival&date=2026-11-13").status_code == 409
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()}


def test_demo_replays_historical_cache_without_weakening_normal_freshness(snapshot, monkeypatch):
    directory, transit, walking = snapshot
    class FutureDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2035, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(store, "datetime", FutureDatetime)
    with TestClient(create_app(transit, walking)) as normal, TestClient(demo.create_demo_app(directory)) as replay:
        assert normal.post("/api/transit/journeys/plan", json=body()).json()["outcome"] == "walking_unavailable"
        assert replay.post("/api/transit/journeys/plan", json=body()).json()["outcome"] == "found"
        walk = replay.get("/api/transit/walking-transfers?from_stop_id=skm:7500&to_stop_id=ztm:2001").json()
        assert walk["status"] == "available" and walk["demo"]["enabled"]
        assert walk["estimate"]["expires_at"].startswith("2026-12-12")


def test_prepare_never_overwrites_existing_output(snapshot):
    directory, transit, walking = snapshot
    before = (directory / "manifest.json").read_bytes()
    with pytest.raises(ValueError, match="już istnieje"):
        demo.prepare(transit, walking, directory)
    assert before == (directory / "manifest.json").read_bytes()


def test_tampered_or_missing_snapshot_is_rejected(snapshot):
    directory, *_ = snapshot
    with (directory / "walking.db").open("ab") as stream:
        stream.write(b"tampered fixture")
    with pytest.raises(ValueError, match="zmieniły"):
        demo.load(directory)


def test_archived_subset_cannot_silently_run_as_normal_data(snapshot):
    directory, *_ = snapshot
    with pytest.raises(ValueError, match="app.demo serve"):
        with TestClient(create_app(directory / "transit.db", directory / "walking.db")):
            pass


def test_manifest_contains_inputs_and_provenance_not_precomputed_results(snapshot):
    directory, *_ = snapshot
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert "results" not in manifest and "evaluation" not in manifest
    assert manifest["provenance"]["walking"][0]["confidence"] == "estimated"
    assert manifest["provenance"]["walking"][0]["license"] == "CC-BY-SA-4.0"
