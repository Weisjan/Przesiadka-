"""Explicit directional interchanges; local schedules and the pure evaluator."""

import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from ..transfer_logic import evaluate_transfer
from ..walking.client import WalkingError, coordinates
from ..walking.store import lookup as walking_lookup
from .schedule import WARSAW, service_datetime
from .store import read_connection, stop_data, stop_departures

MAX_CANDIDATES = 2000


class SearchError(ValueError):
    def __init__(self, status: int, code: str, message: str, **details):
        self.status = status
        self.detail = {"code": code, "message": message, **details}
        super().__init__(message)


@dataclass(frozen=True)
class TransferLink:
    id: str
    arrival_stop_id: str
    departure_stop_id: str
    walking_time_source: str = "estimated"
    note: str = "Jawnie wybrana para; droga i czas dojścia nie zostały zweryfikowane. Feed SKM nie wskazuje peronu."
    approval_status: str = "approved"
    approval_basis: str = "gtfs_stop_and_boarding_audit"
    reviewed_on: str = "2026-11-13"


LINK = TransferLink("gdansk-glowny-skm-ztm-01", "skm:7500", "ztm:2001")
# Approval follows the stop/course audit in docs/transfer-links.md, independently of the walking cache.
LINKS = {link.id: link for link in (
    LINK,
    TransferLink("gdansk-glowny-skm-pks-01", "skm:7500", "ztm:2135"),
    TransferLink("gdansk-glowny-skm-pks-02", "skm:7500", "ztm:2136"),
    TransferLink("gdansk-glowny-skm-ztm-08", "skm:7500", "ztm:1021"),
)}


def find_link(link_id: str) -> TransferLink:
    if link_id not in LINKS:
        raise SearchError(404, "link_not_found", "Nie ma zatwierdzonego powiązania dla tej pary i kierunku. Wybierz powiązanie z transfer-links.")
    return LINKS[link_id]


def iso_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("Podaj dzień kursowania w formacie RRRR-MM-DD.")
    return value


class TransferSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_id: str = Field(min_length=1, max_length=80)
    arrival_trip_id: str = Field(pattern=r"^skm:.+$", max_length=260)
    arrival_service_date: Annotated[date, BeforeValidator(iso_date)]
    arrival_stop_sequence: int | None = Field(default=None, strict=True, ge=0, le=2**31 - 1)
    departure_route_id: str = Field(pattern=r"^ztm:.+$", max_length=260)
    departure_trip_id: str = Field(pattern=r"^ztm:.+$", max_length=260)
    departure_service_date: Annotated[date, BeforeValidator(iso_date)]
    departure_stop_sequence: int | None = Field(default=None, strict=True, ge=0, le=2**31 - 1)
    delay_minutes: float = Field(default=0, strict=True, ge=0, le=30, allow_inf_nan=False)


def linked_stops(connection, link: TransferLink = LINK):
    stops = []
    for stop_id in (link.arrival_stop_id, link.departure_stop_id):
        row = connection.execute("SELECT * FROM gtfs_stops WHERE id=?", (stop_id,)).fetchone()
        if row is None or row["location_type"] != 0 or row["operator"] != stop_id.split(":", 1)[0]:
            raise SearchError(409, "link_unavailable", "Jawne powiązanie wymaga obu konkretnych przystanków typu 0 w lokalnym imporcie.", stop_id=stop_id)
        stops.append(row)
    return stops


def walking_for_link(path: Path, walking_path: Path | None, link: TransferLink, arrival, departure) -> dict:
    if walking_path is None:
        return {"status": "missing", "from_stop_id": link.arrival_stop_id, "to_stop_id": link.departure_stop_id, "estimate": None}
    points = (coordinates(arrival["longitude"], arrival["latitude"]), coordinates(departure["longitude"], departure["latitude"]))
    return walking_lookup(walking_path, path, link.arrival_stop_id, link.departure_stop_id, points=points)


def transfer_links(path: Path, walking_path: Path | None = None) -> dict:
    with read_connection(path) as connection:
        connection.execute("BEGIN")
        links, unavailable = [], []
        for link in LINKS.values():
            try:
                arrival, departure = linked_stops(connection, link)
            except SearchError as error:
                unavailable.append({"id": link.id, **error.detail})
                continue
            try:
                walking = walking_for_link(path, walking_path, link, arrival, departure)
            except WalkingError as error:
                walking = {"status": "error", "message": str(error)}
            links.append({**asdict(link), "arrival_stop": stop_data(arrival), "departure_stop": stop_data(departure), "walking": walking})
        if not links:
            raise SearchError(409, "link_unavailable", "Brak zatwierdzonych powiązań z poprawnymi przystankami w lokalnym imporcie.")
        return {"is_realtime": False, "links": links, "unavailable_links": unavailable}


def service_runs(connection, service_id: str, day: date) -> bool:
    row = connection.execute("""
        SELECT c.*,e.exception_type FROM gtfs_services c
        LEFT JOIN gtfs_exceptions e ON e.service_id=c.id AND e.date=? WHERE c.id=?
    """, (day.isoformat(), service_id)).fetchone()
    if row is None:
        return False
    if row["exception_type"] is not None:
        return row["exception_type"] == 1
    return bool(row["start_date"] and row["start_date"] <= day.isoformat() <= row["end_date"]
                and row["days"] & (1 << day.weekday()))


def require_coverage(metadata: dict, first: date, last: date):
    if first.isoformat() < metadata["service_start_date"] or last.isoformat() > metadata["service_end_date"]:
        raise SearchError(422, "feed_out_of_range", "Żądana data lub pełne okno wyszukiwania jest poza zakresem lokalnego feedu. Zaimportuj właściwy rozkład.",
                          operator=metadata["operator"], service_start_date=metadata["service_start_date"], service_end_date=metadata["service_end_date"])


def journeys(path: Path, leg: Literal["arrival", "departure"], day: date, limit: int,
             after: datetime | None = None, link_id: str = LINK.id) -> dict:
    link = find_link(link_id)
    with read_connection(path) as connection:
        connection.execute("BEGIN")
        arrival, departure = linked_stops(connection, link)
        stop = arrival if leg == "arrival" else departure
        metadata = json.loads(connection.execute("SELECT metadata FROM gtfs_sources WHERE operator=?", (stop["operator"],)).fetchone()[0])
        require_coverage(metadata, day, day)
        if day in (date.min, date.max):
            raise SearchError(422, "unsupported_date", "Data jest poza obsługiwanym zakresem obliczeń czasu.")
        start = datetime.combine(day, time.min, WARSAW).astimezone(timezone.utc)
        end = datetime.combine(day + timedelta(days=1), time.min, WARSAW).astimezone(timezone.utc)
        if after is not None:
            if leg != "departure":
                raise SearchError(422, "invalid_arrival_filter", "Filtr after jest dostępny wyłącznie dla odjazdów.")
            local_day = after.astimezone(WARSAW).date()
            require_coverage(metadata, local_day, local_day)
            anchor = after.astimezone(timezone.utc)
            start, end = max(start, anchor), min(end, anchor + timedelta(hours=6))
        items = stop_departures(connection, stop, metadata, start, end, limit, event=leg) if start < end else []
        return {"is_realtime": False, "realtime_delay": None, "schedule_status": "planned", "leg": leg, "link_id": link.id,
                "date": day.isoformat(), "timezone": "Europe/Warsaw", "stop": stop_data(stop), "source": metadata,
                "journeys": items[:limit], "has_more": len(items) > limit, "limit": limit}


def resolve_arrival(connection, stop_id: str, trip_id: str, service_day: date, stop_sequence: int | None, metadata: dict):
    require_coverage(metadata, service_day, service_day)
    rows = connection.execute("""
        SELECT st.*,t.service_id,t.route_id,t.headsign AS trip_headsign,t.direction_id,r.short_name,r.long_name
        FROM gtfs_stop_times st JOIN gtfs_trips t ON t.id=st.trip_id JOIN gtfs_routes r ON r.id=t.route_id
        WHERE st.trip_id=? AND st.stop_id=? AND (? IS NULL OR st.stop_sequence=?)
        ORDER BY st.stop_sequence LIMIT 2
    """, (trip_id, stop_id, stop_sequence, stop_sequence)).fetchall()
    if not rows:
        raise SearchError(404, "arrival_not_found", "Nie znaleziono tego kursu SKM na wskazanym przystanku.")
    if len(rows) > 1:
        raise SearchError(409, "ambiguous_arrival", "Kurs odwiedza przystanek wielokrotnie. Podaj arrival_stop_sequence.")
    row = rows[0]
    if not service_runs(connection, row["service_id"], service_day):
        raise SearchError(422, "arrival_not_running", "Wybrany kurs SKM nie kursuje w podanym dniu kursowania.")
    if row["arrival_seconds"] is None or row["drop_off_type"] != 0:
        raise SearchError(422, "arrival_not_usable", "Przesiadka wymaga znanego przyjazdu i ogólnodostępnego wysiadania (drop_off_type=0).")
    arrival_at = service_datetime(service_day, row["arrival_seconds"])
    return row, arrival_at


def search_transfers(path: Path, data: TransferSearchInput, walking_path: Path | None = None) -> dict:
    link = find_link(data.link_id)
    with read_connection(path) as connection:
        # Keep both providers, calendars and patterns in one read-only snapshot.
        connection.execute("BEGIN")
        arrival_stop, departure_stop = linked_stops(connection, link)
        walking = walking_for_link(path, walking_path, link, arrival_stop, departure_stop)
        if walking["status"] != "available":
            raise SearchError(422, "walking_time_unavailable", "Brak aktualnego szacunku dojścia dla tej pary.", walking_status=walking["status"])
        walking_minutes = walking["estimate"]["walking_minutes"]
        metadata = {row["operator"]: json.loads(row["metadata"]) for row in connection.execute("SELECT * FROM gtfs_sources")}
        row, arrival_at = resolve_arrival(connection, link.arrival_stop_id, data.arrival_trip_id,
                                         data.arrival_service_date, data.arrival_stop_sequence, metadata["skm"])
        start = arrival_at.astimezone(timezone.utc)
        end = start + timedelta(hours=6)
        require_coverage(metadata["ztm"], start.astimezone(WARSAW).date(), (end - timedelta(microseconds=1)).astimezone(WARSAW).date())
        route = connection.execute("SELECT 1 FROM gtfs_routes WHERE id=? AND operator='ztm'", (data.departure_route_id,)).fetchone()
        if route is None:
            raise SearchError(404, "route_not_found", "Nie znaleziono wskazanej trasy ZTM.")
        if data.departure_service_date is not None:
            require_coverage(metadata["ztm"], data.departure_service_date, data.departure_service_date)
        candidates = stop_departures(connection, departure_stop, metadata["ztm"], start, end, MAX_CANDIDATES, data.departure_route_id)
        if len(candidates) > MAX_CANDIDATES:
            raise SearchError(409, "too_many_departures", "Przekroczono limit kursów w oknie wyszukiwania.")
        selected = [item for item in candidates if item["trip_id"] == data.departure_trip_id
                    and item["service_date"] == data.departure_service_date.isoformat()
                    and (data.departure_stop_sequence is None or item["stop_sequence"] == data.departure_stop_sequence)
                    and item["pickup_type"] == 0]
        if len(selected) != 1:
            raise SearchError(422, "departure_not_available", "Wybrany kurs nie jest dostępny na tym słupku w podanym dniu i oknie czasowym.")
        item = selected[0]
        departure = datetime.fromisoformat(item["departure_at"])
        evaluation = evaluate_transfer(arrival_at, departure, walking_minutes, data.delay_minutes)
        results = [{"departure": item, "evaluation": asdict(evaluation)}]
        return {
            "is_realtime": False, "schedule_status": "planned", "timezone": "Europe/Warsaw",
            "link": {**asdict(link), "walking_minutes": walking_minutes,
                     "walking_time_basis": "openrouteservice_cache", "walking": walking,
                     "arrival_stop": stop_data(arrival_stop), "departure_stop": stop_data(departure_stop)},
            "arrival": {"operator": "skm", "stop_id": link.arrival_stop_id, "stop_name": arrival_stop["name"],
                        "trip_id": data.arrival_trip_id, "route_id": row["route_id"], "service_id": row["service_id"],
                        "service_date": data.arrival_service_date.isoformat(), "stop_sequence": row["stop_sequence"],
                        "line": row["short_name"] or row["long_name"], "direction": row["headsign"] or row["trip_headsign"] or None,
                        "gtfs_arrival_time": row["arrival_time"], "arrival_at": arrival_at.isoformat()},
            "simulated_delay_minutes": data.delay_minutes, "sources": [metadata["skm"], metadata["ztm"]],
            "search_window": {"start_at": arrival_at.isoformat(), "end_at_exclusive": end.astimezone(WARSAW).isoformat()},
            "outcome": "evaluated", "results": results,
            "limitations": ["Czas dojścia jest szacunkowy; peron SKM nie jest określony.", "Opóźnienie jest symulacją, rozkład nie zawiera danych realtime."],
        }
