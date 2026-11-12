"""One explicit interchange; read local schedules and reuse the pure evaluator."""

import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from ..transfer_logic import evaluate_transfer
from .schedule import WARSAW, service_datetime
from .store import read_connection, stop_data, stop_departures

MAX_CANDIDATES = 2000
MAX_PATTERN_STOPS = 1000


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
    walking_time_basis: str = "user_input"
    walking_minutes: None = None
    note: str = "Jawnie wybrana para; droga i czas dojścia nie zostały zweryfikowane. Feed SKM nie wskazuje peronu."


LINK = TransferLink("gdansk-glowny-skm-ztm-01", "skm:7500", "ztm:2001")


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
    # A reference trip selects its downstream variant, not its service date.
    departure_trip_id: str | None = Field(default=None, pattern=r"^ztm:.+$", max_length=260)
    departure_service_date: Annotated[date, BeforeValidator(iso_date)] | None = None
    departure_stop_sequence: int | None = Field(default=None, strict=True, ge=0, le=2**31 - 1)
    walking_minutes: int = Field(strict=True, ge=0, le=180)
    delay_minutes: float = Field(default=0, strict=True, ge=0, le=180, allow_inf_nan=False)
    window_minutes: int = Field(default=120, strict=True, ge=1, le=360)
    limit: int = Field(default=5, strict=True, ge=1, le=10)

    @model_validator(mode="after")
    def validate_departure_selection(self):
        if (self.departure_service_date is not None or self.departure_stop_sequence is not None) and not self.departure_trip_id:
            raise ValueError("Wybór daty lub wystąpienia odjazdu wymaga departure_trip_id.")
        return self


def linked_stops(connection):
    stops = []
    for stop_id in (LINK.arrival_stop_id, LINK.departure_stop_id):
        row = connection.execute("SELECT * FROM gtfs_stops WHERE id=?", (stop_id,)).fetchone()
        if row is None or row["location_type"] != 0:
            raise SearchError(409, "link_unavailable", "Jawne powiązanie wymaga obu konkretnych przystanków typu 0 w lokalnym imporcie.", stop_id=stop_id)
        stops.append(row)
    return stops


def transfer_links(path: Path) -> dict:
    with read_connection(path) as connection:
        connection.execute("BEGIN")
        arrival, departure = linked_stops(connection)
        return {"is_realtime": False, "links": [{**asdict(LINK), "arrival_stop": stop_data(arrival), "departure_stop": stop_data(departure)}]}


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


def variant_key(connection, trip_id: str, sequence: int, direction, headsign):
    rows = connection.execute("""SELECT stop_id,pickup_type,drop_off_type FROM gtfs_stop_times
        WHERE trip_id=? AND stop_sequence>=? ORDER BY stop_sequence LIMIT ?
    """, (trip_id, sequence, MAX_PATTERN_STOPS + 1)).fetchall()
    if len(rows) > MAX_PATTERN_STOPS:
        raise SearchError(409, "pattern_too_large", "Przebieg kursu przekracza limit obsługiwany przez to wyszukiwanie.")
    return direction, headsign, tuple(tuple(row) for row in rows)


def reference_variant(connection, data: TransferSearchInput):
    rows = connection.execute("""
        SELECT st.stop_sequence,st.headsign,t.headsign AS trip_headsign,t.direction_id
        FROM gtfs_stop_times st JOIN gtfs_trips t ON t.id=st.trip_id
        WHERE st.trip_id=? AND st.stop_id=? AND t.route_id=? AND st.pickup_type=0
          AND (? IS NULL OR st.stop_sequence=?)
        ORDER BY st.stop_sequence LIMIT 2
    """, (data.departure_trip_id, LINK.departure_stop_id, data.departure_route_id,
          data.departure_stop_sequence, data.departure_stop_sequence)).fetchall()
    if len(rows) != 1:
        raise SearchError(409, "ambiguous_reference", "Kurs wzorcowy musi jednoznacznie obsługiwać wybrany słupek i trasę z ogólnodostępnym wejściem.")
    row = rows[0]
    return variant_key(connection, data.departure_trip_id, row["stop_sequence"], row["direction_id"], row["headsign"] or row["trip_headsign"] or None)


def require_coverage(metadata: dict, first: date, last: date):
    if first.isoformat() < metadata["service_start_date"] or last.isoformat() > metadata["service_end_date"]:
        raise SearchError(422, "feed_out_of_range", "Żądana data lub pełne okno wyszukiwania jest poza zakresem lokalnego feedu. Zaimportuj właściwy rozkład.",
                          operator=metadata["operator"], service_start_date=metadata["service_start_date"], service_end_date=metadata["service_end_date"])


def journeys(path: Path, leg: Literal["arrival", "departure"], day: date, limit: int,
             after: datetime | None = None) -> dict:
    with read_connection(path) as connection:
        connection.execute("BEGIN")
        arrival, departure = linked_stops(connection)
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
        return {"is_realtime": False, "realtime_delay": None, "schedule_status": "planned", "leg": leg,
                "date": day.isoformat(), "timezone": "Europe/Warsaw", "stop": stop_data(stop), "source": metadata,
                "journeys": items[:limit], "has_more": len(items) > limit, "limit": limit}


def search_transfers(path: Path, data: TransferSearchInput) -> dict:
    if data.link_id != LINK.id:
        raise SearchError(404, "link_not_found", "Nie ma jawnego powiązania tych przystanków. Obsługiwane jest tylko SKM Gdańsk Główny → ZTM Dworzec Główny 01.")
    with read_connection(path) as connection:
        # Keep both providers, calendars and patterns in one read-only snapshot.
        connection.execute("BEGIN")
        arrival_stop, departure_stop = linked_stops(connection)
        metadata = {row["operator"]: json.loads(row["metadata"]) for row in connection.execute("SELECT * FROM gtfs_sources")}
        require_coverage(metadata["skm"], data.arrival_service_date, data.arrival_service_date)
        rows = connection.execute("""
            SELECT st.*,t.service_id,t.route_id,t.headsign AS trip_headsign,t.direction_id,r.short_name,r.long_name
            FROM gtfs_stop_times st JOIN gtfs_trips t ON t.id=st.trip_id JOIN gtfs_routes r ON r.id=t.route_id
            WHERE st.trip_id=? AND st.stop_id=? AND (? IS NULL OR st.stop_sequence=?)
            ORDER BY st.stop_sequence LIMIT 2
        """, (data.arrival_trip_id, LINK.arrival_stop_id, data.arrival_stop_sequence, data.arrival_stop_sequence)).fetchall()
        if not rows:
            raise SearchError(404, "arrival_not_found", "Nie znaleziono tego kursu SKM na wskazanym przystanku.")
        if len(rows) > 1:
            raise SearchError(409, "ambiguous_arrival", "Kurs odwiedza przystanek wielokrotnie. Podaj arrival_stop_sequence.")
        row = rows[0]
        if not service_runs(connection, row["service_id"], data.arrival_service_date):
            raise SearchError(422, "arrival_not_running", "Wybrany kurs SKM nie kursuje w podanym dniu kursowania.")
        if row["arrival_seconds"] is None or row["drop_off_type"] != 0:
            raise SearchError(422, "arrival_not_usable", "Przesiadka wymaga znanego przyjazdu i ogólnodostępnego wysiadania (drop_off_type=0).")
        arrival_at = service_datetime(data.arrival_service_date, row["arrival_seconds"])
        start = arrival_at.astimezone(timezone.utc)
        end = start + timedelta(minutes=data.window_minutes)
        require_coverage(metadata["ztm"], start.astimezone(WARSAW).date(), (end - timedelta(microseconds=1)).astimezone(WARSAW).date())
        route = connection.execute("SELECT 1 FROM gtfs_routes WHERE id=? AND operator='ztm'", (data.departure_route_id,)).fetchone()
        if route is None:
            raise SearchError(404, "route_not_found", "Nie znaleziono wskazanej trasy ZTM.")
        selected_variant = reference_variant(connection, data) if data.departure_trip_id else None
        if data.departure_service_date is not None:
            require_coverage(metadata["ztm"], data.departure_service_date, data.departure_service_date)
        candidates = stop_departures(connection, departure_stop, metadata["ztm"], start, end, MAX_CANDIDATES, data.departure_route_id)
        if len(candidates) > MAX_CANDIDATES:
            raise SearchError(409, "too_many_departures", "Przekroczono limit kursów. Skróć window_minutes.")
        groups = {}
        for item in candidates:
            if item["pickup_type"] != 0:
                continue
            key = variant_key(connection, item["trip_id"], item["stop_sequence"], item["direction_id"], item["direction"])
            if len(key[2]) < 2:  # No downstream stop: do not propose boarding at a terminus.
                continue
            groups.setdefault(key, []).append(item)
        if selected_variant is None and len(groups) > 1:
            choices = [{"departure_trip_id": items[0]["trip_id"], "direction_id": key[0], "direction": key[1],
                        "downstream_stop_ids": [stop[0] for stop in key[2]], "first_departure_at": items[0]["departure_at"]}
                       for key, items in groups.items()]
            raise SearchError(409, "ambiguous_departure_variant", "Trasa ma kilka kierunków lub przebiegów. Wybierz departure_trip_id jako wzorzec wariantu; nie dopasowujemy po samej nazwie.",
                              choices=choices[:20], has_more_choices=len(choices) > 20)
        matching = groups.get(selected_variant, []) if selected_variant is not None else next(iter(groups.values()), [])
        selected = matching
        if data.departure_service_date is not None:
            selected = [item for item in matching if item["trip_id"] == data.departure_trip_id
                        and item["service_date"] == data.departure_service_date.isoformat()
                        and (data.departure_stop_sequence is None or item["stop_sequence"] == data.departure_stop_sequence)]
            if len(selected) != 1:
                raise SearchError(422, "departure_not_available", "Wybrany odjazd nie jest jednoznacznie dostępny w oknie do 6 godzin od przyjazdu. Sprawdź datę, kurs i kolejność przystanków.")
        results = []
        for item in selected[:data.limit]:
            departure = datetime.fromisoformat(item["departure_at"])
            later = [candidate for candidate in matching
                     if datetime.fromisoformat(candidate["departure_at"]).astimezone(timezone.utc) > departure.astimezone(timezone.utc)]
            evaluation = evaluate_transfer(arrival_at, departure, data.walking_minutes, data.delay_minutes,
                                           [datetime.fromisoformat(candidate["departure_at"]) for candidate in later])
            alternatives = [candidate for candidate in later if datetime.fromisoformat(candidate["departure_at"]).astimezone(timezone.utc)
                            == evaluation.plan_b_departure_at.astimezone(timezone.utc)] if evaluation.plan_b_departure_at else []
            if len(alternatives) > 1:
                raise SearchError(409, "ambiguous_plan_b", "Kilka zgodnych kursów ma ten sam moment odjazdu Planu B. Nie wybieramy arbitralnie identyfikatora kursu.", choices=alternatives)
            plan_b = alternatives[0] if alternatives else None
            results.append({"departure": item, "evaluation": asdict(evaluation), "plan_b": plan_b})
        return {
            "is_realtime": False, "schedule_status": "planned", "timezone": "Europe/Warsaw",
            "link": {**asdict(LINK), "walking_minutes": data.walking_minutes,
                     "arrival_stop": stop_data(arrival_stop), "departure_stop": stop_data(departure_stop)},
            "arrival": {"operator": "skm", "stop_id": LINK.arrival_stop_id, "stop_name": arrival_stop["name"],
                        "trip_id": data.arrival_trip_id, "route_id": row["route_id"], "service_id": row["service_id"],
                        "service_date": data.arrival_service_date.isoformat(), "stop_sequence": row["stop_sequence"],
                        "line": row["short_name"] or row["long_name"], "direction": row["headsign"] or row["trip_headsign"] or None,
                        "gtfs_arrival_time": row["arrival_time"], "arrival_at": arrival_at.isoformat()},
            "simulated_delay_minutes": data.delay_minutes, "sources": [metadata["skm"], metadata["ztm"]],
            "search_window": {"start_at": arrival_at.isoformat(), "end_at_exclusive": end.astimezone(WARSAW).isoformat()},
            "outcome": "evaluated" if results else "no_departures", "results": results,
            "limit": data.limit, "has_more": len(selected) > data.limit,
            "limitations": ["Dojście jest szacunkiem użytkownika; peron SKM i dostępność drogi nie są zweryfikowane.",
                            "Plan B obejmuje tylko wskazany słupek, tę samą trasę, kierunek i dalszy przebieg w podanym oknie.",
                            "Brak alternatywy oznacza brak zgodnego kursu w tym oknie; rozkład nie uwzględnia zmian realtime."],
        }
