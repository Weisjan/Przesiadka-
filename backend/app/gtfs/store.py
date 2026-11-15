import json
import math
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from .schedule import MAX_TIME_SECONDS, WARSAW, service_anchor, service_datetime
from .sources import GTFSError, SOURCES

APPLICATION_ID = 0x50524754
SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS gtfs_sources(operator TEXT PRIMARY KEY, metadata TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS gtfs_agencies(
 id TEXT PRIMARY KEY, operator TEXT NOT NULL REFERENCES gtfs_sources ON DELETE CASCADE,
 name TEXT NOT NULL, url TEXT NOT NULL, timezone TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS gtfs_stops(
 id TEXT PRIMARY KEY, operator TEXT NOT NULL REFERENCES gtfs_sources ON DELETE CASCADE,
 source_stop_id TEXT NOT NULL, name TEXT NOT NULL, search_name TEXT NOT NULL,
 latitude REAL, longitude REAL, code TEXT NOT NULL, location_type INTEGER NOT NULL,
 parent_station TEXT REFERENCES gtfs_stops(id) ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS gtfs_services(
 id TEXT PRIMARY KEY, operator TEXT NOT NULL REFERENCES gtfs_sources ON DELETE CASCADE,
 days INTEGER NOT NULL DEFAULT 0, start_date TEXT, end_date TEXT);
CREATE TABLE IF NOT EXISTS gtfs_exceptions(
 service_id TEXT NOT NULL REFERENCES gtfs_services(id) ON DELETE CASCADE,
 date TEXT NOT NULL, exception_type INTEGER NOT NULL CHECK(exception_type IN (1,2)),
 PRIMARY KEY(service_id,date));
CREATE TABLE IF NOT EXISTS gtfs_routes(
 id TEXT PRIMARY KEY, operator TEXT NOT NULL REFERENCES gtfs_sources ON DELETE CASCADE,
 agency_id TEXT NOT NULL REFERENCES gtfs_agencies(id) ON DELETE CASCADE,
 short_name TEXT NOT NULL, long_name TEXT NOT NULL, route_type INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS gtfs_trips(
 id TEXT PRIMARY KEY, operator TEXT NOT NULL REFERENCES gtfs_sources ON DELETE CASCADE,
 route_id TEXT NOT NULL REFERENCES gtfs_routes(id) ON DELETE CASCADE,
 service_id TEXT NOT NULL REFERENCES gtfs_services(id) ON DELETE CASCADE,
 headsign TEXT NOT NULL, direction_id INTEGER, short_name TEXT NOT NULL, block_id TEXT, shape_id TEXT);
CREATE TABLE IF NOT EXISTS gtfs_stop_times(
 trip_id TEXT NOT NULL REFERENCES gtfs_trips(id) ON DELETE CASCADE,
 stop_id TEXT NOT NULL REFERENCES gtfs_stops(id) ON DELETE CASCADE,
 stop_sequence INTEGER NOT NULL, arrival_seconds INTEGER, departure_seconds INTEGER,
 arrival_time TEXT NOT NULL, departure_time TEXT NOT NULL, headsign TEXT NOT NULL,
 pickup_type INTEGER NOT NULL, drop_off_type INTEGER NOT NULL,
 PRIMARY KEY(trip_id,stop_sequence));
CREATE INDEX IF NOT EXISTS gtfs_stop_departures ON gtfs_stop_times(stop_id,departure_seconds);
CREATE INDEX IF NOT EXISTS gtfs_trip_source ON gtfs_trips(operator);
CREATE INDEX IF NOT EXISTS gtfs_source_stops ON gtfs_stops(operator);
"""


def normalize_search(value: str) -> str:
    return "".join(character for character in unicodedata.normalize("NFKD", value.casefold().replace("ł", "l"))
                   if not unicodedata.combining(character))


def write_connection(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        connection = sqlite3.connect(path, timeout=10)
    except sqlite3.Error as error:
        raise GTFSError("Nie można otworzyć osobnej bazy GTFS do importu.") from error
    try:
        application = connection.execute("PRAGMA application_id").fetchone()[0]
        tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if (application != APPLICATION_ID and tables) or application not in (0, APPLICATION_ID):
            raise GTFSError("Odmowa zapisu: to nie jest baza GTFS Przesiadka+. Dane scenariuszy pozostają bez zmian.")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if application == APPLICATION_ID and version != SCHEMA_VERSION:
            raise GTFSError("Nieobsługiwana wersja bazy GTFS. Importuj do nowej, osobnej bazy.")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(SCHEMA)
        connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        connection.row_factory = sqlite3.Row
        return connection
    except sqlite3.Error as error:
        connection.close()
        raise GTFSError("Nieprawidłowa lub niedostępna baza GTFS. Istniejący plik nie zostanie zastąpiony.") from error
    except Exception:
        connection.close()
        raise


@contextmanager
def read_connection(path: Path):
    if not path.is_file():
        raise GTFSError("Brak lokalnej bazy GTFS. Uruchom jawny import CLI.")
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            if (connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID
                    or connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION):
                raise GTFSError("Nieprawidłowa lub nieobsługiwana lokalna baza GTFS.")
            yield connection
        finally:
            connection.close()
    except sqlite3.Error as error:
        raise GTFSError("Lokalna baza GTFS jest niedostępna lub uszkodzona.") from error


def sources(path: Path) -> list[dict]:
    imported = {}
    if path.exists():
        with read_connection(path) as connection:
            imported = {row["operator"]: json.loads(row["metadata"]) for row in connection.execute("SELECT * FROM gtfs_sources")}
    return [{**source.metadata(), "is_realtime": False, "imported": key in imported, **imported.get(key, {})}
            for key, source in SOURCES.items()]


def stop_data(row: sqlite3.Row) -> dict:
    return {
        "operator": row["operator"], "operator_name": SOURCES[row["operator"]].name,
        "stop_id": row["id"], "source_stop_id": row["source_stop_id"], "stop_name": row["name"],
        "latitude": row["latitude"], "longitude": row["longitude"], "stop_code": row["code"],
        "location_type": row["location_type"], "parent_station": row["parent_station"],
    }


def search_stops(path: Path, query: str, limit: int) -> list[dict]:
    normalized = normalize_search(query.strip()).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    with read_connection(path) as connection:
        rows = connection.execute("SELECT * FROM gtfs_stops WHERE search_name LIKE ? ESCAPE '\\' ORDER BY search_name,id LIMIT ?",
                                  (f"%{normalized}%", limit)).fetchall()
        return [stop_data(row) for row in rows]


def stop_departures(connection: sqlite3.Connection, stop, metadata: dict,
                    start: datetime, end: datetime, limit: int, route_id: str | None = None,
                    event: str = "departure") -> list[dict]:
    """Bounded UTC interval; retain service dates and GTFS extended times."""
    if event not in ("arrival", "departure"):
        raise ValueError("Unsupported timetable event")
    column = "arrival_seconds" if event == "arrival" else "departure_seconds"
    permission = "drop_off_type=0" if event == "arrival" else "pickup_type<>1"
    first_service = date.fromisoformat(metadata["service_start_date"]).toordinal()
    last_service = date.fromisoformat(metadata["service_end_date"]).toordinal()
    max_days = (MAX_TIME_SECONDS if event == "arrival" else metadata["max_departure_seconds"]) // 86400 + 1
    first = max(first_service, start.astimezone(WARSAW).date().toordinal() - max_days)
    last = min(last_service, end.astimezone(WARSAW).date().toordinal() + 1)
    items = []
    for ordinal in range(first, last + 1):
        service_day = date.fromordinal(ordinal)
        anchor = service_anchor(service_day)
        lower = max(0, math.ceil((start - anchor).total_seconds()))
        upper = math.ceil((end - anchor).total_seconds())
        rows = connection.execute(f"""
          SELECT st.*,t.id AS trip_id,t.service_id,t.headsign AS trip_headsign,t.direction_id,
                 r.id AS route_id,r.short_name,r.long_name,r.route_type
          FROM gtfs_stop_times st JOIN gtfs_trips t ON t.id=st.trip_id
          JOIN gtfs_routes r ON r.id=t.route_id JOIN gtfs_services c ON c.id=t.service_id
          LEFT JOIN gtfs_exceptions e ON e.service_id=t.service_id AND e.date=?
          WHERE st.stop_id=? AND st.{column}>=? AND st.{column}<? AND st.{permission}
            AND (? IS NULL OR t.route_id=?)
            AND (e.exception_type=1 OR (e.exception_type IS NULL AND c.start_date<=? AND c.end_date>=? AND c.days & ? <> 0))
          ORDER BY st.{column},t.id,st.stop_sequence LIMIT ?
        """, (service_day.isoformat(), stop["id"], lower, upper, route_id, route_id,
              service_day.isoformat(), service_day.isoformat(), 1 << service_day.weekday(), limit + 1)).fetchall()
        for row in rows:
            departure = service_datetime(service_day, row["departure_seconds"]) if row["departure_seconds"] is not None else None
            items.append({
                "operator": stop["operator"], "operator_name": SOURCES[stop["operator"]].name,
                "stop_id": stop["id"], "stop_name": stop["name"], "route_id": row["route_id"],
                "line": row["short_name"] or row["long_name"], "route_type": row["route_type"],
                "direction": row["headsign"] or row["trip_headsign"] or None,
                "direction_id": row["direction_id"], "trip_id": row["trip_id"], "service_id": row["service_id"],
                "service_date": service_day.isoformat(), "stop_sequence": row["stop_sequence"],
                "gtfs_departure_time": row["departure_time"], "gtfs_arrival_time": row["arrival_time"],
                "departure_at": departure.isoformat() if departure else None,
                "arrival_at": service_datetime(service_day, row["arrival_seconds"]).isoformat() if row["arrival_seconds"] is not None else None,
                "pickup_type": row["pickup_type"], "drop_off_type": row["drop_off_type"],
            })
    items.sort(key=lambda item: (datetime.fromisoformat(item[f"{event}_at"]).astimezone(timezone.utc), item["trip_id"], item["stop_sequence"]))
    return items[:limit + 1]


def departures(path: Path, stop_id: str, day: date, limit: int) -> dict | None:
    with read_connection(path) as connection:
        stop = connection.execute("SELECT * FROM gtfs_stops WHERE id=?", (stop_id,)).fetchone()
        if stop is None:
            return None
        metadata = json.loads(connection.execute("SELECT metadata FROM gtfs_sources WHERE operator=?", (stop["operator"],)).fetchone()[0])
        result = {"is_realtime": False, "date": day.isoformat(), "timezone": "Europe/Warsaw", "source": metadata,
                  "stop": stop_data(stop), "departures": [], "limit": limit, "has_more": False}
        ordinal = day.toordinal()
        first = date.fromisoformat(metadata["service_start_date"]).toordinal()
        last = date.fromisoformat(metadata["service_end_date"]).toordinal()
        if ordinal < first - 1 or ordinal > last + metadata["max_departure_seconds"] // 86400 + 1:
            return result
        day_start = datetime.combine(day, time.min, WARSAW).astimezone(timezone.utc)
        if day == date.max:
            return result
        next_day = day + timedelta(days=1)
        day_end = datetime.combine(next_day, time.min, WARSAW).astimezone(timezone.utc)
        items = stop_departures(connection, stop, metadata, day_start, day_end, limit)
        result["has_more"] = len(items) > limit
        result["departures"] = items[:limit]
        return result
