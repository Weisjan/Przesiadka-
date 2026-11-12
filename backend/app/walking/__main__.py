import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..gtfs.sources import GTFSError, configured_path as transit_path
from .client import WalkingError, fetch_walking
from .store import configured_path, freshness, read_saved, save_result, stop_pair

SUPPORTED_PAIRS = {("skm:7500", "ztm:2001")}


def request_limit(value: str) -> int:
    if value not in ("1", "2", "3"):
        raise argparse.ArgumentTypeError("Limit musi wynosić 1–3, łącznie z ponowieniami.")
    return int(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jawny import szacunku dojścia ORS dla jednej kierunkowej pary; klucz wyłącznie z ORS_API_KEY.")
    parser.add_argument("from_stop_id")
    parser.add_argument("to_stop_id")
    parser.add_argument("--dry-run", action="store_true", help="Pokaż identyfikatory i [longitude,latitude], bez sieci i zapisu.")
    parser.add_argument("--refresh", action="store_true", help="Jawnie odśwież także aktualny wynik.")
    parser.add_argument("--max-requests", type=request_limit, default=2, help="Łączny budżet prób ORS dla tej jednej pary (domyślnie 2).")
    parser.add_argument("--database", type=Path, default=configured_path(), help="Osobna baza dojścia, nigdy baza scenariuszy lub GTFS.")
    parser.add_argument("--transit-database", type=Path, default=transit_path(), help="Odczyt współrzędnych z istniejącej bazy GTFS.")
    args = parser.parse_args(argv)
    try:
        if (args.from_stop_id, args.to_stop_id) not in SUPPORTED_PAIRS:
            raise WalkingError("unsupported_pair", "Na tym etapie importer obsługuje wyłącznie skm:7500 -> ztm:2001. Nie wykonano żądania ORS.")
        points = stop_pair(args.transit_database, args.from_stop_id, args.to_stop_id)
        saved = read_saved(args.database, args.from_stop_id, args.to_stop_id)
        current = bool(saved and freshness(saved, points, datetime.now(timezone.utc)))
        print(json.dumps({"from_stop_id": args.from_stop_id, "to_stop_id": args.to_stop_id, "coordinates": points,
                          "profile": "foot-walking", "cache_current": current,
                          "dry_run": args.dry_run, "max_requests": args.max_requests}, ensure_ascii=False), flush=True)
        if args.dry_run:
            return 0
        if current and not args.refresh:
            print(json.dumps({"action": "cached", "result": saved}, ensure_ascii=False))
            return 0
        result = fetch_walking(*points, max_requests=args.max_requests)
        row = save_result(args.database, args.from_stop_id, args.to_stop_id, points, result)
        print(json.dumps({"action": "saved", "result": row}, ensure_ascii=False))
        return 0
    except (WalkingError, GTFSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except OSError:
        print("Nie można odczytać lub zapisać lokalnej bazy dojścia. Nie zapisano nowego wyniku.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
