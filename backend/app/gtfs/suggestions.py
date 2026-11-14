"""Bounded suggestions across approved SKM → ZTM links, using local data only."""

import json
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from ..transfer_logic import evaluate_transfer
from ..walking.client import WalkingError
from .schedule import WARSAW
from .store import normalize_search, read_connection, stop_data, stop_departures
from .transfer_search import (
    LINKS, MAX_CANDIDATES, SearchError, iso_date, linked_stops, require_coverage,
    resolve_arrival, walking_for_link,
)


class SuggestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    arrival_stop_id: str = Field(pattern=r"^skm:.+$", max_length=260)
    arrival_trip_id: str = Field(pattern=r"^skm:.+$", max_length=260)
    arrival_service_date: Annotated[date, BeforeValidator(iso_date)]
    arrival_stop_sequence: int = Field(strict=True, ge=0, le=2**31 - 1)
    query: str = Field(default="", max_length=120)
    limit: int = Field(default=12, strict=True, ge=1, le=20)
    delay_minutes: float = Field(default=0, strict=True, ge=0, le=30, allow_inf_nan=False)


def matches_words(words: list[str], text: str) -> bool:
    text = normalize_search(text)
    for word in words:
        # Route-like tokens use whole words, so N1 does not match N10.
        if any(character.isdecimal() for character in word):
            if word not in text.split():
                return False
        elif word not in text:
            return False
    return True


def match_course(query: str, departure: dict, downstream: list[dict]) -> dict | None:
    """Destination matches require a usable later stop on this exact trip."""
    words = normalize_search(query).split()
    line = normalize_search(departure["line"])
    if not downstream:
        return None
    if normalize_search(query).strip() == line:
        return {"kind": "line"}
    if len(words) == 1 and words[0].isdecimal():
        return {"kind": "line"} if words[0] == line else None
    for stop in downstream:
        if words and matches_words(words, f"{departure['line']} {stop['stop_name']}"):
            return {"kind": "stop", "stop_id": stop["stop_id"], "stop_name": stop["stop_name"]}
    direction = departure["direction"] or ""
    if direction and matches_words(words, f"{departure['line']} {direction}"):
        return {"kind": "direction"}
    return None


def ranking_key(item: dict) -> tuple:
    margin = item["evaluation"]["margin_minutes"]
    band = 0 if margin >= 2 else 1 if margin >= 0 else 2
    departure = item["departure"]
    instant = datetime.fromisoformat(departure["departure_at"]).astimezone(timezone.utc)
    return (band, margin, instant, item["link"]["walking_minutes"], item["link"]["id"],
            departure["route_id"], departure["trip_id"], departure["service_date"], departure["stop_sequence"])


def suggest_transfers(path: Path, data: SuggestionInput, walking_path: Path) -> dict:
    links = [link for link in LINKS.values() if link.arrival_stop_id == data.arrival_stop_id]
    if not links:
        raise SearchError(404, "link_not_found", "Ta stacja SKM nie ma zatwierdzonych przesiadek ZTM.")
    with read_connection(path) as connection:
        connection.execute("BEGIN")
        metadata = {row["operator"]: json.loads(row["metadata"]) for row in connection.execute("SELECT * FROM gtfs_sources")}
        if not all(operator in metadata for operator in ("skm", "ztm")):
            raise SearchError(503, "feed_missing", "Zaimportuj lokalne rozkłady SKM i ZTM.")
        arrival_row, arrival_at = resolve_arrival(connection, data.arrival_stop_id, data.arrival_trip_id,
                                                data.arrival_service_date, data.arrival_stop_sequence, metadata["skm"])
        start = arrival_at.astimezone(timezone.utc)
        end = start + timedelta(hours=6)
        require_coverage(metadata["ztm"], start.astimezone(WARSAW).date(), (end - timedelta(microseconds=1)).astimezone(WARSAW).date())
        candidates, excluded = [], []
        downstream_by_occurrence = {}
        for link in links:
            try:
                arrival_stop, departure_stop = linked_stops(connection, link)
                walking = walking_for_link(path, walking_path, link, arrival_stop, departure_stop)
            except (SearchError, WalkingError) as error:
                excluded.append({"link_id": link.id, "status": "unavailable", "message": str(error)})
                continue
            if walking["status"] != "available":
                excluded.append({"link_id": link.id, "status": walking["status"], "message": "Brak aktualnego szacunku dojścia."})
                continue
            departures = stop_departures(connection, departure_stop, metadata["ztm"], start, end, MAX_CANDIDATES)
            if len(departures) > MAX_CANDIDATES:
                raise SearchError(409, "too_many_departures", "Przekroczono limit kursów w oknie wyszukiwania.")
            for departure in departures:
                if departure["pickup_type"] != 0:
                    continue
                occurrence = (departure["trip_id"], departure["stop_sequence"])
                if occurrence not in downstream_by_occurrence:
                    downstream_by_occurrence[occurrence] = [dict(row) for row in connection.execute("""
                        SELECT s.id AS stop_id,s.name AS stop_name FROM gtfs_stop_times st
                        JOIN gtfs_stops s ON s.id=st.stop_id
                        WHERE st.trip_id=? AND st.stop_sequence>? AND st.drop_off_type=0 AND st.arrival_seconds IS NOT NULL
                        ORDER BY st.stop_sequence,s.id
                    """, occurrence)]
                match = match_course(data.query, departure, downstream_by_occurrence[occurrence])
                if match is None:
                    continue
                minutes = walking["estimate"]["walking_minutes"]
                evaluation = evaluate_transfer(arrival_at, datetime.fromisoformat(departure["departure_at"]), minutes, data.delay_minutes)
                candidates.append({"link": {**asdict(link), "arrival_stop": stop_data(arrival_stop),
                                            "departure_stop": stop_data(departure_stop), "walking": walking, "walking_minutes": minutes},
                                   "departure": departure, "evaluation": asdict(evaluation), "match": match})
        candidates.sort(key=ranking_key)
        reachable = [item for item in candidates if item["evaluation"]["margin_minutes"] >= 0]
        directions = []
        seen = set()
        for item in reachable:
            departure = item["departure"]
            identity = (departure["line"], departure["direction"])
            goal = f"{departure['line']} {departure['direction']}"
            if identity not in seen and departure["direction"] and len(goal) <= 120:
                seen.add(identity)
                directions.append({"line": departure["line"], "direction": departure["direction"],
                                   "query": goal})
        recommendation = reachable[0] if data.query and reachable else None
        reason = None
        if recommendation:
            reason = ("Preferowany zapas co najmniej 2 min, następnie najkrótsze oczekiwanie po dojściu."
                      if recommendation["evaluation"]["margin_minutes"] >= 2 else
                      "Brak kursu z zapasem 2 min. To najkrótsze oczekiwanie wśród osiągalnych kursów.")
        if not data.query:
            outcome = "choose_destination"
        elif recommendation:
            outcome = "recommended"
        elif candidates:
            outcome = "no_reachable"
        else:
            outcome = "no_match"
        if not candidates and excluded and len(excluded) == len(links):
            outcome = "walking_unavailable"
        return {"is_realtime": False, "schedule_status": "planned", "query": data.query,
                "arrival": {"stop_id": data.arrival_stop_id, "trip_id": data.arrival_trip_id,
                            "service_date": data.arrival_service_date.isoformat(), "stop_sequence": arrival_row["stop_sequence"],
                            "route_id": arrival_row["route_id"], "arrival_at": arrival_at.isoformat()},
                "outcome": outcome, "recommendation": recommendation, "reason": reason,
                "results": candidates[:data.limit] if data.query else [], "has_more": len(candidates) > data.limit,
                "directions": directions[:12], "excluded_links": excluded,
                "simulated_delay_minutes": data.delay_minutes,
                "search_window": {"start_at": arrival_at.isoformat(), "end_at_exclusive": end.astimezone(WARSAW).isoformat()},
                "limitations": ["Dojście jest szacunkowe; feed SKM nie określa peronu.",
                                "Wyłącznie zatwierdzone powiązania i lokalne rozkłady planowane, bez realtime."]}
