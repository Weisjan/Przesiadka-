"""One SKM ride, an approved walk and one ZTM ride. Local read-only data."""

import json
import re
from time import monotonic
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from ..transfer_logic import evaluate_transfer
from ..walking.client import WalkingError
from .schedule import WARSAW, service_datetime
from .store import normalize_search, read_connection, stop_data, stop_departures
from .transfer_search import LINKS, MAX_CANDIDATES, SearchError, iso_date, linked_stops, require_coverage, walking_for_link

MAX_TRAINS = 200
MAX_COMBINATIONS = 50_000
WINDOW_HOURS = 6
StopIDs = Annotated[list[str], Field(min_length=1, max_length=32)]


class PlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    origin_stop_id: str | None = Field(default=None, pattern=r"^skm:.+$", max_length=260)
    destination_stop_id: str | None = Field(default=None, pattern=r"^ztm:.+$", max_length=260)
    origin_stop_ids: StopIDs | None = None
    destination_stop_ids: StopIDs | None = None
    departure_date: Annotated[date, BeforeValidator(iso_date)]
    departure_time: str = Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    departure_offset: Literal["+01:00", "+02:00"] | None = None
    max_results: int = Field(default=3, strict=True, ge=1, le=3)

    @model_validator(mode="after")
    def validate_stops(self):
        for name, prefix in (("origin", "skm:"), ("destination", "ztm:")):
            single, group = getattr(self, f"{name}_stop_id"), getattr(self, f"{name}_stop_ids")
            if (single is None) == (group is None):
                raise ValueError(f"Podaj jeden przystanek lub grupę przystanków: {name}.")
            values = group if group is not None else [single]
            if any(not isinstance(value, str) or not value.startswith(prefix) or not 0 < len(value) <= 260 or value == prefix for value in values):
                raise ValueError("Nieprawidłowy identyfikator przystanku lub operator.")
            setattr(self, f"{name}_stop_ids", sorted(set(values)))
        return self


def requested_instant(data: PlanInput) -> datetime:
    wall = datetime.combine(data.departure_date, time.fromisoformat(data.departure_time))
    if not 2 <= wall.year <= 9998:
        raise SearchError(422, "unsupported_date", "Data jest poza obsługiwanym zakresem.")
    options = {}
    for fold in (0, 1):
        candidate = wall.replace(tzinfo=WARSAW, fold=fold)
        if candidate.astimezone(timezone.utc).astimezone(WARSAW).replace(tzinfo=None) == wall:
            options[candidate.strftime("%z")] = candidate
    if not options:
        raise SearchError(422, "nonexistent_time", "Ta godzina nie istnieje w Warszawie z powodu zmiany czasu.")
    if data.departure_offset:
        selected = options.get(data.departure_offset.replace(":", ""))
        if selected is None:
            raise SearchError(422, "invalid_offset", "Offset nie odpowiada wybranej dacie i godzinie w Warszawie.")
        return selected
    if len(options) > 1:
        raise SearchError(422, "ambiguous_time", "Ta godzina występuje dwukrotnie. Wybierz UTC+02:00 lub UTC+01:00.")
    return next(iter(options.values()))


def planner_stops(path: Path, operator: Literal["skm", "ztm"], query: str, limit: int) -> dict:
    """Group only exact station names / ZTM numbered poles, never walking links."""
    words = normalize_search(query).split()
    groups = {}
    with read_connection(path) as connection:
        for row in connection.execute("SELECT * FROM gtfs_stops WHERE operator=? AND location_type=0 ORDER BY name,id", (operator,)):
            name = re.sub(r"\s+[0-9]{2}$", "", row["name"]) if operator == "ztm" else row["name"]
            key = normalize_search(name)
            if all(word in key for word in words):
                group = groups.setdefault(key, {"name": name, "operator": operator, "stops": []})
                group["stops"].append(stop_data(row))
    ordered = sorted(groups.values(), key=lambda item: (normalize_search(item["name"]), item["name"]))
    return {"is_realtime": False, "groups": ordered[:limit], "has_more": len(ordered) > limit}


def later_stops(connection, journey: dict, ids: list[str]) -> list[dict]:
    placeholders = ",".join("?" for _ in ids)
    rows = connection.execute(f"""
        SELECT st.*,s.name FROM gtfs_stop_times st JOIN gtfs_stops s ON s.id=st.stop_id
        WHERE st.trip_id=? AND st.stop_sequence>? AND st.stop_id IN ({placeholders})
          AND st.drop_off_type=0 AND st.arrival_seconds IS NOT NULL ORDER BY st.stop_sequence LIMIT ?
    """, (journey["trip_id"], journey["stop_sequence"], *ids, MAX_CANDIDATES + 1)).fetchall()
    if len(rows) > MAX_CANDIDATES:
        raise SearchError(409, "search_limit_exceeded", "Zbyt wiele postojów jednego kursu.")
    day = date.fromisoformat(journey["service_date"])
    return [{**journey, "stop_id": row["stop_id"], "stop_name": row["name"], "stop_sequence": row["stop_sequence"],
             "arrival_at": service_datetime(day, row["arrival_seconds"]).isoformat(),
             "departure_at": service_datetime(day, row["departure_seconds"]).isoformat() if row["departure_seconds"] is not None else None,
             "gtfs_arrival_time": row["arrival_time"], "gtfs_departure_time": row["departure_time"],
             "direction": row["headsign"] or journey["direction"], "pickup_type": row["pickup_type"], "drop_off_type": row["drop_off_type"]}
            for row in rows]


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def ranking_key(item: dict) -> tuple:
    return (0 if item["evaluation"]["margin_minutes"] >= 2 else 1,
            instant(item["destination"]["arrival_at"]), item["total_minutes"], item["waiting_minutes"],
            item["origin"]["trip_id"], item["origin"]["service_date"], item["origin"]["stop_sequence"],
            item["link"]["id"], item["arrival"]["stop_sequence"], item["departure"]["trip_id"],
            item["departure"]["service_date"], item["departure"]["stop_sequence"], item["destination"]["stop_sequence"])


def plan_journey(path: Path, data: PlanInput, walking_path: Path, walking_at: datetime | None = None) -> dict:
    start = requested_instant(data).astimezone(timezone.utc)
    end = start + timedelta(hours=WINDOW_HOURS)
    with read_connection(path) as connection:
        deadline = monotonic() + 8
        connection.set_progress_handler(lambda: monotonic() > deadline, 10_000)
        connection.execute("BEGIN")
        metadata = {row["operator"]: json.loads(row["metadata"]) for row in connection.execute("SELECT * FROM gtfs_sources")}
        if not all(operator in metadata for operator in ("skm", "ztm")):
            raise SearchError(503, "feed_missing", "Brak lokalnych rozkładów SKM i ZTM. Wykonaj import opisany w README.")
        for source in metadata.values():
            require_coverage(source, start.astimezone(WARSAW).date(), (end - timedelta(microseconds=1)).astimezone(WARSAW).date())
        origins, destinations = [], []
        for ids, operator, target in ((data.origin_stop_ids, "skm", origins), (data.destination_stop_ids, "ztm", destinations)):
            for stop_id in ids:
                row = connection.execute("SELECT * FROM gtfs_stops WHERE id=? AND operator=? AND location_type=0", (stop_id, operator)).fetchone()
                if row is None:
                    raise SearchError(404, "stop_not_found", "Nie znaleziono wybranej stacji lub przystanku w lokalnym rozkładzie.")
                target.append(row)
        trains = []
        for origin in origins:
            occurrences = stop_departures(connection, origin, metadata["skm"], start, end, MAX_TRAINS)
            if len(occurrences) > MAX_TRAINS:
                raise SearchError(409, "search_limit_exceeded", "Zbyt wiele pociągów w oknie. Zmień godzinę wyszukiwania.")
            trains.extend(occurrences)
        if len(trains) > MAX_TRAINS:
            raise SearchError(409, "search_limit_exceeded", "Zbyt wiele pociągów w oknie. Wybierz konkretniejszą stację lub późniejszą godzinę.")
        trains = [train for train in trains if train["pickup_type"] == 0]

        links, excluded = {}, []
        for link in LINKS.values():
            try:
                arrival_stop, departure_stop = linked_stops(connection, link)
                walking = walking_for_link(path, walking_path, link, arrival_stop, departure_stop, walking_at)
                if walking["status"] != "available":
                    excluded.append({"link_id": link.id, "status": walking["status"]})
                    continue
                links[link.id] = {**asdict(link), "arrival_stop": stop_data(arrival_stop), "departure_stop": stop_data(departure_stop),
                                  "walking": walking, "walking_minutes": walking["estimate"]["walking_minutes"]}
            except (SearchError, WalkingError) as error:
                excluded.append({"link_id": link.id, "status": "unavailable", "message": str(error)})

        transfers_by_trip, departures_by_stop, goals_by_trip = {}, {}, {}
        candidates, seen = [], set()
        checked, has_link, has_walking, has_goal = 0, False, False, False
        transfer_ids = sorted({link.arrival_stop_id for link in LINKS.values()})
        if len(LINKS) > 100:
            raise SearchError(409, "search_limit_exceeded", "Rejestr przesiadek przekracza limit tego planera.")
        for origin in trains:
            occurrence = (origin["trip_id"], origin["service_date"], origin["stop_sequence"])
            if occurrence not in transfers_by_trip:
                transfers_by_trip[occurrence] = later_stops(connection, origin, transfer_ids) if transfer_ids else []
            for arrival in transfers_by_trip[occurrence]:
                arrival_at = instant(arrival["arrival_at"])
                if not start <= instant(origin["departure_at"]) <= arrival_at < end:
                    continue
                for registered in LINKS.values():
                    if registered.arrival_stop_id != arrival["stop_id"]:
                        continue
                    has_link = True
                    link = links.get(registered.id)
                    if link is None:
                        continue
                    has_walking = True
                    stop_id = registered.departure_stop_id
                    if stop_id not in departures_by_stop:
                        stop = connection.execute("SELECT * FROM gtfs_stops WHERE id=?", (stop_id,)).fetchone()
                        departures = stop_departures(connection, stop, metadata["ztm"], start, end, MAX_CANDIDATES)
                        if len(departures) > MAX_CANDIDATES:
                            raise SearchError(409, "search_limit_exceeded", "Zbyt wiele odjazdów ZTM w oknie wyszukiwania.")
                        departures_by_stop[stop_id] = departures
                    for departure in departures_by_stop[stop_id]:
                        departure_at = instant(departure["departure_at"])
                        if departure["pickup_type"] != 0 or departure_at < arrival_at:
                            continue
                        checked += 1
                        if checked > MAX_COMBINATIONS:
                            raise SearchError(409, "search_limit_exceeded", "Przekroczono limit porównywanych podróży. Wybierz późniejszą godzinę.")
                        dep_key = (departure["trip_id"], departure["service_date"], departure["stop_sequence"])
                        if dep_key not in goals_by_trip:
                            goals_by_trip[dep_key] = sorted(later_stops(connection, departure, data.destination_stop_ids), key=lambda stop: (instant(stop["arrival_at"]), stop["stop_sequence"]))
                        for destination in goals_by_trip[dep_key]:
                            checked += 1
                            if checked > MAX_COMBINATIONS:
                                raise SearchError(409, "search_limit_exceeded", "Przekroczono limit porównywanych podróży.")
                            goal_at = instant(destination["arrival_at"])
                            if not departure_at <= goal_at < end:
                                continue
                            has_goal = True
                            evaluation = evaluate_transfer(arrival_at, departure_at, link["walking_minutes"], 0)
                            if evaluation.margin_minutes < 0:
                                continue
                            # A named destination group may occur twice on a trip; keep its earliest usable arrival.
                            identity = (*occurrence, registered.id, arrival["stop_sequence"], *dep_key)
                            if identity in seen:
                                continue
                            seen.add(identity)
                            candidates.append({"origin": origin, "arrival": arrival, "link": link, "departure": departure,
                                               "destination": destination, "evaluation": asdict(evaluation),
                                               "total_minutes": (goal_at - instant(origin["departure_at"])).total_seconds() / 60,
                                               "elapsed_from_request_minutes": (goal_at - start).total_seconds() / 60,
                                               "initial_wait_minutes": (instant(origin["departure_at"]) - start).total_seconds() / 60,
                                               "waiting_minutes": evaluation.margin_minutes,
                                               "risk": "estimated" if evaluation.margin_minutes >= 2 else "tight"})
        candidates.sort(key=ranking_key)
        if candidates:
            outcome = "found"
        elif not trains:
            outcome = "no_skm"
        elif not has_link:
            outcome = "no_transfer_link"
        elif not has_walking:
            outcome = "walking_unavailable"
        else:
            outcome = "no_reachable" if has_goal else "no_destination_service"
        return {"is_realtime": False, "schedule_status": "planned", "timezone": "Europe/Warsaw", "outcome": outcome,
                "origin_stop_ids": data.origin_stop_ids, "destination_stop_ids": data.destination_stop_ids,
                "requested_departure_at": start.astimezone(WARSAW).isoformat(),
                "search_window": {"start_at": start.astimezone(WARSAW).isoformat(), "end_at_exclusive": end.astimezone(WARSAW).isoformat()},
                "results": candidates[:data.max_results], "has_more": len(candidates) > data.max_results,
                "sources": [{**source, "imported": True, "is_realtime": False} for source in metadata.values()], "excluded_links": excluded,
                "scope": {"approved_links": len(LINKS), "available_links": len(links), "trains_checked": len(trains), "combinations_checked": checked},
                "reason": "Najpierw zapas co najmniej 2 min, potem wcześniejsze dotarcie do celu, krótsza podróż i oczekiwanie.",
                "limitations": ["Najlepszy wynik tylko wśród aktualnie obsługiwanych, zatwierdzonych połączeń w oknie 6 godzin; nie jest to globalnie najszybsza trasa.",
                                "Dojście jest szacunkowe. Feed SKM nie określa peronu; nie gwarantujemy przesiadki.",
                                "Rozkłady planowane z lokalnego GTFS. Opóźnienie jest wyłącznie symulacją."]}
