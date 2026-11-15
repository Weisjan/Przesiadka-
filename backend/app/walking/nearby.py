"""Geographic candidates are not validated walking links or journey-planner edges."""

import heapq
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from ..gtfs.store import read_connection, stop_data
from .client import WalkingError, coordinates
from .store import freshness, read_saved

EARTH_RADIUS_M = 6371008.8
MAX_RADIUS_M = 2000
MAX_CANDIDATES = 100


def haversine(start, end) -> float:
    lon1, lat1 = map(math.radians, coordinates(*start))
    lon2, lat2 = map(math.radians, coordinates(*end))
    value = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1, max(0, value))))


def nearby(transit: Path, walking: Path, stop_id: str, radius_m: float = 500, limit: int = 50) -> dict:
    if (isinstance(radius_m, bool) or not isinstance(radius_m, (int, float)) or not math.isfinite(radius_m)
            or not 0 < radius_m <= MAX_RADIUS_M or isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_CANDIDATES):
        raise WalkingError("invalid_parameters", "Promień musi wynosić >0–2000 m, a limit 1–100.")
    rejected = Counter()
    total = 0
    with read_connection(transit) as database:
        database.execute("BEGIN")
        origin = database.execute("SELECT * FROM gtfs_stops WHERE id=?", (stop_id,)).fetchone()
        if origin is None:
            raise WalkingError("stop_not_found", "Nie znaleziono przystanku początkowego.")
        if origin["location_type"] != 0 or origin["operator"] not in ("skm", "ztm"):
            raise WalkingError("invalid_stop", "Wybierz konkretny przystanek ZTM lub SKM typu location_type=0.")
        start = coordinates(origin["longitude"], origin["latitude"])
        target_operator = "ztm" if origin["operator"] == "skm" else "skm"

        def candidates():
            nonlocal total
            for row in database.execute("SELECT * FROM gtfs_stops WHERE operator=?", (target_operator,)):
                if row["location_type"] != 0:
                    rejected["not_boarding_stop"] += 1
                    continue
                try:
                    end = coordinates(row["longitude"], row["latitude"])
                except WalkingError:
                    rejected["invalid_coordinates"] += 1
                    continue
                distance = haversine(start, end)
                if distance > radius_m:
                    rejected["outside_radius"] += 1
                    continue
                total += 1
                yield distance, row["id"], stop_data(row), end

        selected = heapq.nsmallest(limit, candidates(), key=lambda item: (item[0], item[1]))
        origin_data = stop_data(origin)
    now = datetime.now(timezone.utc)
    results = []
    for distance, target_id, target, end in selected:
        saved = read_saved(walking, stop_id, target_id)
        status = "missing" if saved is None else saved["status"] if freshness(saved, (start, end), now) else "stale"
        results.append({"from_stop_id": stop_id, "to_stop_id": target_id, "from_stop": origin_data, "to_stop": target,
                        "straight_line_distance_m": distance, "has_saved_result": saved is not None,
                        "has_saved_walking_route": bool(saved and saved["status"] == "available"), "status": status,
                        "walking_seconds": saved["walking_seconds"] if saved else None,
                        "source": saved["source"] if saved else None, "confidence": saved["confidence"] if saved else None,
                        "estimate": saved, "coordinates": [list(start), list(end)]})
    return {"stop": origin_data, "radius_m": radius_m, "distance_method": "haversine",
            "candidate_count": total, "returned_count": len(results), "limit": limit, "has_more": total > limit,
            "cache_hits": sum(item["status"] in ("available", "no_route") for item in results),
            "rejected": dict(rejected), "candidates": results,
            "limitations": ["Odległość w linii prostej służy tylko do wyboru kandydatów; nie określa czasu dojścia.",
                            "Przystanek SKM może nie wskazywać konkretnego peronu. Kandydaci nie stają się automatycznie powiązaniami przesiadkowymi."]}
