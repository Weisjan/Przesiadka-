import io
import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError

import pytest

from app.walking import candidates, client, store
from app.walking.nearby import haversine, nearby
from gtfs_fixtures import files, setup_feed

PAIR = ("skm:7500", "ztm:2001")
RESULT = {"status": "available", "distance_m": 213.5, "walking_seconds": 153.7}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def prohibited(*a, **k): raise AssertionError("No real ORS calls in tests")
    monkeypatch.setattr(client, "open_request", prohibited)
    monkeypatch.setenv("ORS_API_KEY", "fictional-nearby-test-key")


def test_haversine_known_distance_zero_antimeridian_and_symmetry():
    assert haversine((0, 0), (0, 1)) == pytest.approx(111195.08, abs=.1)
    assert haversine((18, 54), (18, 54)) == 0
    assert haversine((179.999, 0), (-179.999, 0)) == pytest.approx(222.39, abs=.1)
    assert haversine((18, 54), (19, 55)) == haversine((19, 55), (18, 54))


def test_radius_includes_boundary_and_excludes_just_beyond(tmp_path, setup_feed):
    transit = setup_feed()
    with sqlite3.connect(transit) as c:
        c.execute("UPDATE gtfs_stops SET latitude=55 WHERE operator='ztm'")
        c.execute("UPDATE gtfs_stops SET latitude=54.001 WHERE id='ztm:2001'")
    radius = haversine((18, 54), (18, 54.001))
    assert nearby(transit, tmp_path/'walking.db', PAIR[0], radius)["candidate_count"] == 1
    assert nearby(transit, tmp_path/'walking.db', PAIR[0], radius - .000001)["candidate_count"] == 0


def test_ids_codes_operators_same_names_and_zero_distance_are_not_merged(tmp_path, setup_feed):
    transit, walking = setup_feed(), tmp_path/'walking.db'
    data = nearby(transit, walking, PAIR[0])
    ids = [item['to_stop_id'] for item in data['candidates']]
    assert 'ztm:2001' in ids and 'ztm:2002' in ids and 'ztm:7500' in ids
    assert len(ids) == len(set(ids))
    assert all(item['to_stop']['operator'] == 'ztm' and item['walking_seconds'] is None for item in data['candidates'])
    assert all(item['straight_line_distance_m'] == 0 for item in data['candidates'])
    assert all('stop_code' in item['to_stop'] and item['to_stop']['location_type'] == 0 for item in data['candidates'])
    reverse = nearby(transit, walking, PAIR[1])
    assert all(item['to_stop']['operator'] == 'skm' for item in reverse['candidates'])
    assert not walking.exists()


def test_missing_coordinates_and_nonboarding_stations_are_reported(tmp_path, setup_feed):
    transit = setup_feed()
    with sqlite3.connect(transit) as c:
        c.execute("UPDATE gtfs_stops SET latitude=NULL WHERE id='ztm:2002'")
    data = nearby(transit, tmp_path/'walk.db', PAIR[0])
    assert data['rejected']['invalid_coordinates'] == 1
    assert data['rejected']['not_boarding_stop'] == 1
    assert 'ztm:2002' not in [item['to_stop_id'] for item in data['candidates']]


def test_cache_direction_fresh_stale_no_route_and_coordinate_reimport(tmp_path, setup_feed):
    transit, walking = setup_feed(), tmp_path/'walking.db'
    points = store.stop_pair(transit, *PAIR)
    store.save_result(walking, *PAIR, points, RESULT)
    def find(): return next(item for item in nearby(transit, walking, PAIR[0])['candidates'] if item['to_stop_id'] == PAIR[1])
    assert find()['status'] == 'available' and find()['walking_seconds'] == 153.7
    reverse = next(item for item in nearby(transit, walking, PAIR[1])['candidates'] if item['to_stop_id'] == PAIR[0])
    assert reverse['status'] == 'missing'
    store.save_result(walking, *PAIR, points, RESULT, datetime.now(timezone.utc)-timedelta(days=31))
    assert find()['status'] == 'stale'
    store.save_result(walking, *PAIR, points, {'status':'no_route','distance_m':None,'walking_seconds':None})
    assert find()['status'] == 'no_route' and find()['walking_seconds'] is None
    assert not find()['has_saved_walking_route']
    store.save_result(walking, *PAIR, points, RESULT)
    updated = files('ztm'); updated['stops.txt'] = updated['stops.txt'].replace('54,18', '54.0001,18')
    setup_feed(ztm=updated)
    assert find()['status'] == 'stale'


def test_candidate_limit_counts_all_and_dry_run_never_writes(tmp_path, setup_feed, capsys):
    transit, walking = setup_feed(), tmp_path/'walking.db'
    full = nearby(transit, walking, PAIR[0])
    limited = nearby(transit, walking, PAIR[0], limit=1)
    assert limited['has_more'] and limited['candidate_count'] == full['candidate_count']
    plan = candidates.run(transit, walking, PAIR[0], max_pairs=2, max_requests=1)
    assert plan['dry_run'] and plan['selected_pairs'] == 2 and plan['planned_initial_requests'] == 1
    assert plan['requests_made'] == 0 and not walking.exists()
    assert 'fictional-nearby-test-key' not in capsys.readouterr().out


@pytest.mark.parametrize('changes', [{'radius_m':float('nan')},{'radius_m':0},{'radius_m':2001},{'limit':101},
                                    {'max_pairs':21},{'max_requests':0},{'max_requests':21},{'interval_seconds':.1},{'interval_seconds':float('nan')}])
def test_hard_limits_before_network(tmp_path, setup_feed, changes):
    with pytest.raises(client.WalkingError): candidates.run(setup_feed(), tmp_path/'walk.db', PAIR[0], **changes)


def test_global_retry_budget_rate_limiter_and_resume(tmp_path, setup_feed, monkeypatch, capsys):
    transit, walking = setup_feed(), tmp_path/'walking.db'
    calls, sleeps = [], []
    clock = [0.0]
    monkeypatch.setattr(candidates.time, 'monotonic', lambda: clock[0])
    def sleep(seconds): sleeps.append(seconds); clock[0] += seconds
    monkeypatch.setattr(candidates.time, 'sleep', sleep)
    def respond(*a, **k):
        calls.append(1)
        if len(calls) == 1: raise HTTPError(client.ENDPOINT,503,'busy',{},io.BytesIO())
        return io.BytesIO(json.dumps({'routes':[{'summary':{'distance':213.5,'duration':153.7}}]}).encode())
    monkeypatch.setattr(client,'open_request',respond)
    plan = candidates.run(transit, walking, PAIR[0], max_pairs=3, max_requests=3, execute=True)
    assert plan['requests_made'] == 3 and plan['saved_pairs'] == 2 and len(calls) == 3
    assert plan['remaining_selected_pairs'] == 1 and plan['stopped_reason'] == 'request_budget'
    assert sum(sleeps) >= 4  # A minimum two seconds between every actual attempt, including retry.
    again = candidates.run(transit, walking, PAIR[0], max_pairs=1, max_requests=1, execute=True)
    assert again['cache_hits'] == 2 and again['saved_pairs'] == 1
    assert len(calls) == 4
    assert 'fictional-nearby-test-key' not in capsys.readouterr().out


@pytest.mark.parametrize('status,headers', [(429,{}),(503,{'Retry-After':'120'}),(401,{}),(403,{})])
def test_rate_limit_and_auth_stop_entire_batch(tmp_path, setup_feed, monkeypatch, status, headers):
    calls=[]
    def fail(*a,**k):
        calls.append(1)
        raise HTTPError(client.ENDPOINT,status,'private provider text',headers,io.BytesIO())
    monkeypatch.setattr(client,'open_request',fail)
    monkeypatch.setattr(client.time,'sleep',lambda _:None)
    walking=tmp_path/'walking.db'
    plan=candidates.run(setup_feed(),walking,PAIR[0],max_pairs=3,max_requests=10,execute=True)
    assert len(calls)==1 and plan['errors'] and not walking.exists()

def test_refresh_recalculates_only_when_explicit_and_missing_key_never_counts_a_request(tmp_path, setup_feed, monkeypatch):
    transit, walking = setup_feed(), tmp_path/'walking.db'
    first = nearby(transit, walking, PAIR[0], limit=1)['candidates'][0]
    store.save_result(walking, first['from_stop_id'], first['to_stop_id'], first['coordinates'], RESULT)
    cached = candidates.run(transit, walking, PAIR[0], limit=1)
    refreshed = candidates.run(transit, walking, PAIR[0], limit=1, refresh=True)
    assert cached['selected_pairs']==0 and refreshed['selected_pairs']==1
    monkeypatch.delenv('ORS_API_KEY')
    before=walking.read_bytes()
    failed=candidates.run(transit,walking,PAIR[0],limit=1,refresh=True,execute=True)
    assert failed['requests_made']==0 and failed['errors'][0]['code']=='missing_key'
    assert walking.read_bytes()==before
