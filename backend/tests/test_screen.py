from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.transfer_logic import evaluate_transfer
from app.walking import store, client
from gtfs_fixtures import files, setup_feed

@pytest.mark.parametrize("delay,margin,status", [(0,6,"Zdążysz"),(6,0,"Na styk"),(8,-2,"Nie zdążysz")])
def test_evaluation(delay,margin,status):
    result=evaluate_transfer(datetime.fromisoformat("2026-11-13T17:42:00+01:00"),datetime.fromisoformat("2026-11-13T17:51:00+01:00"),3,delay)
    assert result.margin_minutes==margin and result.status==status

@pytest.mark.parametrize("arrival,departure", [("2026-11-13T23:58:00+01:00","2026-11-14T00:07:00+01:00"),("2026-03-29T01:58:00+01:00","2026-03-29T03:07:00+02:00"),("2026-10-25T02:58:00+02:00","2026-10-25T02:07:00+01:00")])
def test_midnight_dst(arrival,departure):
    assert evaluate_transfer(datetime.fromisoformat(arrival),datetime.fromisoformat(departure),3,6).margin_minutes==0

@pytest.mark.parametrize("state", ["available","missing","stale","no_route"])
def test_screen_cache_exact_course_and_retired_routes(tmp_path,setup_feed,monkeypatch,state):
    transit=setup_feed();walking=tmp_path/"walking.db"
    monkeypatch.setattr(client,"open_request",lambda *a,**k:pytest.fail("ORS forbidden"))
    pair=("skm:7500","ztm:2001")
    if state!="missing":
        result={"status":"available","distance_m":200.5,"walking_seconds":153.7} if state!="no_route" else {"status":"no_route","distance_m":None,"walking_seconds":None}
        store.save_result(walking,*pair,store.stop_pair(transit,*pair),result,datetime.now(timezone.utc)-timedelta(days=31 if state=="stale" else 0))
    payload={"link_id":"gdansk-glowny-skm-ztm-01","arrival_trip_id":"skm:a","arrival_service_date":"2026-11-12","departure_route_id":"ztm:8","departure_trip_id":"ztm:a","departure_service_date":"2026-11-12","delay_minutes":8}
    with TestClient(create_app(transit,walking)) as api:
        response=api.post("/api/transit/transfers/search",json=payload)
        assert response.status_code==(200 if state=="available" else 422),response.text
        if state=="available":
            data=response.json();assert data["results"][0]["evaluation"]["margin_minutes"]==-2
            assert "plan_b" not in str(data)
            assert api.post("/api/transit/transfers/search",json={**payload,"departure_trip_id":"ztm:wrong"}).status_code==422
            assert api.post("/api/transit/transfers/search",json={**payload,"delay_minutes":31}).status_code==422
        for route in ["/api/scenarios","/api/transfers/evaluate","/api/transit/nearby-stops","/api/transit/stops"]:
            assert api.get(route).status_code==404

def test_database_paths_cannot_alias(tmp_path):
    with pytest.raises(ValueError,match="osobne"):
        with TestClient(create_app(tmp_path/"same.db",tmp_path/"same.db")):pass
    assert not (tmp_path/"same.db").exists()
