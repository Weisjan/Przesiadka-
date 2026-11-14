import math
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..gtfs.store import read_connection
from .client import ATTRIBUTION, ENDPOINT, LICENSE, LICENSE_URL, PROFILE, TERMS_CHECKED_ON, TERMS_URL, WalkingError, coordinates, parse_response

DEFAULT_DATABASE = Path(__file__).resolve().parents[2] / "data" / "walking.db"
APPLICATION_ID = 0x5052574B
SCHEMA_VERSION = 1
MAX_AGE = timedelta(days=30)
NO_ROUTE_MAX_AGE = timedelta(days=1)
SCHEMA = """CREATE TABLE walking_transfers(
 from_stop_id TEXT NOT NULL, to_stop_id TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('available','no_route')),
 distance_m REAL, walking_seconds REAL, source TEXT NOT NULL,
 confidence TEXT NOT NULL CHECK(confidence='estimated'), calculated_at TEXT NOT NULL, expires_at TEXT NOT NULL,
 from_longitude REAL NOT NULL, from_latitude REAL NOT NULL, to_longitude REAL NOT NULL, to_latitude REAL NOT NULL,
 profile TEXT NOT NULL, endpoint TEXT NOT NULL, attribution TEXT NOT NULL,
 license TEXT NOT NULL, license_url TEXT NOT NULL, terms_url TEXT NOT NULL, terms_checked_on TEXT NOT NULL,
 PRIMARY KEY(from_stop_id,to_stop_id), CHECK(from_stop_id<>to_stop_id),
 CHECK((status='no_route' AND distance_m IS NULL AND walking_seconds IS NULL)
 OR (status='available' AND distance_m>0 AND walking_seconds>0)))"""


def configured_path() -> Path:
    return Path(os.environ.get("PRZESIADKA_WALKING_PATH", str(DEFAULT_DATABASE))).resolve()


def stop_pair(transit: Path, from_stop_id: str, to_stop_id: str) -> tuple[tuple[float, float], tuple[float, float]]:
    if from_stop_id == to_stop_id:
        raise WalkingError("invalid_pair", "Wybierz dwa różne przystanki.")
    with read_connection(transit) as connection:
        connection.execute("BEGIN")
        result = []
        for stop_id in (from_stop_id, to_stop_id):
            row = connection.execute("SELECT longitude,latitude,location_type FROM gtfs_stops WHERE id=?", (stop_id,)).fetchone()
            if row is None:
                raise WalkingError("stop_not_found", "Nie znaleziono wskazanego przystanku w lokalnym GTFS.")
            if row["location_type"] != 0:
                raise WalkingError("invalid_stop", "Dojście wymaga konkretnych przystanków typu location_type=0.")
            result.append(coordinates(row["longitude"], row["latitude"]))
        return tuple(result)


@contextmanager
def connection(path: Path, write=False):
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
    elif not path.is_file():
        yield None
        return
    database = None
    try:
        database = sqlite3.connect(path if write else path.resolve().as_uri() + "?mode=ro", uri=not write, timeout=5)
        database.row_factory = sqlite3.Row
        application = database.execute("PRAGMA application_id").fetchone()[0]
        version = database.execute("PRAGMA user_version").fetchone()[0]
        tables = database.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if application == APPLICATION_ID and version == SCHEMA_VERSION:
            pass
        elif write and application == 0 and not tables and version == 0:
            database.execute("BEGIN IMMEDIATE")
            database.execute(SCHEMA)
            database.execute(f"PRAGMA application_id={APPLICATION_ID}")
            database.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        else:
            raise WalkingError("invalid_database", "Odmowa dostępu: to nie jest osobna baza szacunków dojścia. Bazy GTFS i scenariuszy nie zostaną zmienione.")
        yield database
        if write:
            database.commit()
    except sqlite3.Error:
        raise WalkingError("database_unavailable", "Osobna baza szacunków dojścia jest niedostępna lub uszkodzona.") from None
    finally:
        if database is not None:
            database.close()


def read_saved(path: Path, from_stop_id: str, to_stop_id: str) -> dict | None:
    with connection(path) as database:
        row = database.execute("SELECT * FROM walking_transfers WHERE from_stop_id=? AND to_stop_id=?", (from_stop_id, to_stop_id)).fetchone() if database else None
        if row is None:
            return None
        result = dict(row)
        try:
            dates = [datetime.fromisoformat(result[field]) for field in ("calculated_at", "expires_at")]
            if any(value.tzinfo is None for value in dates) or dates[1] <= dates[0]:
                raise ValueError
            if result["source"] != "openrouteservice" or result["confidence"] != "estimated":
                raise ValueError
            if result["status"] == "available":
                parse_response({"routes": [{"summary": {"distance": result["distance_m"], "duration": result["walking_seconds"]}}]})
            elif result["status"] != "no_route" or result["distance_m"] is not None or result["walking_seconds"] is not None:
                raise ValueError
        except (ValueError, TypeError):
            raise WalkingError("invalid_cache", "Zapisany szacunek dojścia zawiera nieprawidłowe dane. Odśwież go jawnym importem.") from None
        return result


def freshness(row: dict, points, now: datetime) -> bool:
    actual = (row["from_longitude"], row["from_latitude"], row["to_longitude"], row["to_latitude"])
    return (actual == (*points[0], *points[1]) and row["profile"] == PROFILE and row["endpoint"] == ENDPOINT
            and row["license"] == LICENSE and row["terms_checked_on"] == TERMS_CHECKED_ON
            and datetime.fromisoformat(row["calculated_at"]) <= now < datetime.fromisoformat(row["expires_at"]))


def save_result(path: Path, from_stop_id: str, to_stop_id: str, points, result: dict,
                now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if from_stop_id == to_stop_id or now.tzinfo is None:
        raise WalkingError("invalid_result", "Nieprawidłowa para przystanków lub data wyliczenia.")
    start, end = coordinates(*points[0]), coordinates(*points[1])
    if result.get("status") == "available":
        result = parse_response({"routes": [{"summary": {"distance": result.get("distance_m"), "duration": result.get("walking_seconds")}}]})
    elif result != {"status": "no_route", "distance_m": None, "walking_seconds": None}:
        raise WalkingError("invalid_result", "Nieprawidłowy stan wyniku dojścia.")
    row = {"from_stop_id": from_stop_id, "to_stop_id": to_stop_id, **result, "source": "openrouteservice", "confidence": "estimated",
           "calculated_at": now.astimezone(timezone.utc).isoformat(),
           "expires_at": (now + (MAX_AGE if result["status"] == "available" else NO_ROUTE_MAX_AGE)).astimezone(timezone.utc).isoformat(),
           "from_longitude": start[0], "from_latitude": start[1], "to_longitude": end[0], "to_latitude": end[1],
           "profile": PROFILE, "endpoint": ENDPOINT, "attribution": ATTRIBUTION, "license": LICENSE, "license_url": LICENSE_URL,
           "terms_url": TERMS_URL, "terms_checked_on": TERMS_CHECKED_ON}
    with connection(path, write=True) as database:
        columns = list(row)
        updates = ','.join(f"{column}=excluded.{column}" for column in columns[2:])
        database.execute(f"INSERT INTO walking_transfers ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)}) ON CONFLICT(from_stop_id,to_stop_id) DO UPDATE SET {updates}", tuple(row.values()))
    return row


def lookup(path: Path, transit: Path, from_stop_id: str, to_stop_id: str, now: datetime | None = None,
           *, points=None) -> dict:
    points = stop_pair(transit, from_stop_id, to_stop_id) if points is None else points
    row = read_saved(path, from_stop_id, to_stop_id)
    if row is None:
        return {"status": "missing", "from_stop_id": from_stop_id, "to_stop_id": to_stop_id, "estimate": None}
    current = freshness(row, points, now or datetime.now(timezone.utc))
    return {"status": row["status"] if current else "stale", "from_stop_id": from_stop_id, "to_stop_id": to_stop_id,
            "estimate": {**row, "walking_minutes": math.ceil(row["walking_seconds"] / 60) if row["walking_seconds"] is not None else None,
                         "rounding": "ceil_to_full_minutes"}, "reason": None if current else "expired_or_coordinates_changed"}
