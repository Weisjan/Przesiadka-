"""Explicit, offline preparation and serving of an isolated historical demo."""

import argparse
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from .gtfs.planner import PlanInput, plan_journey, planner_stops
from .gtfs.sources import DEFAULT_DATABASE as TRANSIT_DEFAULT, GTFSError, configured_path
from .gtfs.store import read_connection, stop_departures
from .gtfs.transfer_search import LINKS, linked_stops, walking_for_link
from .walking import store
from .walking.client import WalkingError

DEFAULT_DIRECTORY = Path(__file__).resolve().parents[1] / "data" / "demo"
START = "2026-11-13T16:00:00+01:00"
END = "2026-11-14T00:00:00+01:00"
PROFILES = (
    ("strzyza", "Strzyża PKM", "Tramwaj i alternatywne kursy"),
    ("lawendowe", "Lawendowe Wzgórze", "Mały zapas i inny słupek"),
    ("przegalina", "Przegalina", "Przesiadka na autobus"),
)
ORIGIN_NAME = "GDAŃSK WRZESZCZ"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def exact_group(path: Path, operator: str, name: str) -> dict:
    groups = planner_stops(path, operator, name, 100)["groups"]
    matches = [group for group in groups if group["name"].casefold() == name.casefold()]
    if len(matches) != 1:
        raise ValueError(f"Archiwum nie zawiera jednoznacznego przystanku: {name}.")
    return matches[0]


def prepare(transit: Path, walking: Path, output: Path) -> dict:
    """Read official imported data; write only to a new, separate directory."""
    transit, walking, output = transit.resolve(), walking.resolve(), output.resolve()
    if output.exists():
        raise ValueError("Katalog demo już istnieje. Zachowano go bez zmian; wybierz nowy katalog --output.")
    if not walking.is_file():
        raise ValueError("Brak zapisanej bazy ORS. Przygotowanie demo nie pobiera tras z sieci.")
    origin = exact_group(transit, "skm", ORIGIN_NAME)
    examples = [{"id": key, "name": f"Wrzeszcz → {name}", "description": description,
                 "origin": origin, "destination": exact_group(transit, "ztm", name),
                 "departure_date": "2026-11-13", "departure_time": "17:00"}
                for key, name, description in PROFILES]
    saved = [store.read_saved(walking, link.arrival_stop_id, link.departure_stop_id) for link in LINKS.values()]
    if not saved or any(row is None for row in saved):
        raise ValueError("Demo wymaga zapisanych pomiarów ORS dla wszystkich zatwierdzonych powiązań.")
    reference = max(datetime.fromisoformat(row["calculated_at"]) for row in saved)
    with read_connection(transit) as source:
        source.execute("BEGIN")
        metadata = {row["operator"]: json.loads(row["metadata"]) for row in source.execute("SELECT * FROM gtfs_sources")}
        if set(metadata) != {"skm", "ztm"}:
            raise ValueError("Zaimportuj oba oficjalne rozkłady przed przygotowaniem demo.")
        for link in LINKS.values():
            a, b = linked_stops(source, link)
            if walking_for_link(transit, walking, link, a, b, reference)["status"] != "available":
                raise ValueError("Pomiary ORS nie mają wspólnego poprawnego stanu historycznego lub współrzędne zmieniły się.")
        kept = set()
        stops = list(source.execute("SELECT * FROM gtfs_stops WHERE operator='skm' AND location_type=0"))
        stops += [linked_stops(source, link)[1] for link in LINKS.values()]
        for stop in stops:
            occurrences = stop_departures(source, stop, metadata[stop["operator"]], datetime.fromisoformat(START), datetime.fromisoformat(END), 2000)
            if len(occurrences) > 2000:
                raise ValueError("Wycinek przekracza limit przygotowania demo; nie utworzono częściowych danych.")
            kept.update(item["trip_id"] for item in occurrences)
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".demo-build-", dir=output.parent) as temporary:
            stage = Path(temporary) / "snapshot"
            stage.mkdir()
            with closing(sqlite3.connect(stage / "transit.db")) as target:
                source.backup(target)
            with store.connection(walking) as source_walk, closing(sqlite3.connect(stage / "walking.db")) as target:
                source_walk.backup(target)
            with closing(sqlite3.connect(stage / "transit.db")) as target:
                target.execute("PRAGMA foreign_keys=ON")
                target.execute("CREATE TEMP TABLE keep_trip(id TEXT PRIMARY KEY)")
                target.executemany("INSERT INTO keep_trip VALUES (?)", [(trip,) for trip in sorted(kept)])
                target.execute("DELETE FROM gtfs_trips WHERE NOT EXISTS(SELECT 1 FROM keep_trip WHERE keep_trip.id=gtfs_trips.id)")
                for operator, original in metadata.items():
                    original["demo_subset"] = {"window_start_at": START, "window_end_at": END,
                        "retained_trips": target.execute("SELECT count(*) FROM gtfs_trips WHERE operator=?", (operator,)).fetchone()[0],
                        "note": "Archiwalny wycinek; pozostałe metadane opisują oryginalny import."}
                    target.execute("UPDATE gtfs_sources SET metadata=? WHERE operator=?", (json.dumps(original, ensure_ascii=False), operator))
                target.commit()
                if target.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("Niespójny wycinek danych; nie utworzono demo.")
                target.execute("VACUUM")
            # Validate by executing the same planner, never by storing calculated answers.
            for example in examples:
                data = PlanInput(origin_stop_ids=[s["stop_id"] for s in example["origin"]["stops"]],
                                 destination_stop_ids=[s["stop_id"] for s in example["destination"]["stops"]],
                                 departure_date=example["departure_date"], departure_time=example["departure_time"])
                result = plan_journey(stage / "transit.db", data, stage / "walking.db", reference)
                if not result["results"]:
                    raise ValueError(f"Przykład nie działa w tym archiwum: {example['name']}.")
            demo = {"enabled": True, "label": "Archiwalne demo · 13 listopada 2026 · to nie jest aktualny rozkład",
                    "window_start_at": START, "window_end_at": END, "walking_reference_at": reference.isoformat(),
                    "departure_date": "2026-11-13", "min_departure_time": "16:00", "max_departure_time": "18:00", "examples": examples}
            manifest = {"format": 1, "demo": demo, "files": {name: digest(stage / name) for name in ("transit.db", "walking.db")},
                        "provenance": {"gtfs": metadata, "walking": saved},
                        "redistribution": "Local archive only. Provider production dates are not confirmed; do not publish this bundle without resolving attribution requirements. ORS results retain CC BY-SA 4.0."}
            (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            # rename refuses an existing destination on Windows; never replace a snapshot.
            stage.rename(output)
    return {"directory": str(output), "examples": [example["name"] for example in examples],
            "bytes": sum((output / name).stat().st_size for name in ("transit.db", "walking.db", "manifest.json"))}


def load(directory: Path) -> dict:
    directory = directory.resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != 1:
        raise ValueError("Nieobsługiwana wersja zestawu demo.")
    for name in ("transit.db", "walking.db"):
        path = directory / name
        if path.resolve().parent != directory or not path.is_file() or digest(path) != manifest["files"][name]:
            raise ValueError("Pliki demo zmieniły się lub są niekompletne. Użyj zachowanego zestawu.")
        for original in (TRANSIT_DEFAULT, store.DEFAULT_DATABASE):
            if original.exists() and path.samefile(original):
                raise ValueError("Demo nie może używać oryginalnej bazy użytkownika.")
    demo = manifest["demo"]
    if demo.get("enabled") is not True or demo.get("window_start_at") != START or demo.get("window_end_at") != END:
        raise ValueError("Nieprawidłowy zakres archiwalnego demo.")
    reference = datetime.fromisoformat(demo["walking_reference_at"])
    if reference.tzinfo is None or not 1 <= len(demo["examples"]) <= 3:
        raise ValueError("Nieprawidłowy stan historyczny demo.")
    return demo


def create_demo_app(directory: Path):
    from .main import create_app
    demo = load(directory)
    return create_app(directory / "transit.db", directory / "walking.db", demo=demo)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Lokalne, archiwalne demo bez sieci i zapisów do baz użytkownika.")
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--transit", type=Path, default=configured_path())
    prepare_parser.add_argument("--walking", type=Path, default=store.configured_path())
    prepare_parser.add_argument("--output", type=Path, default=DEFAULT_DIRECTORY)
    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    serve_parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            print(json.dumps(prepare(args.transit, args.walking, args.output), ensure_ascii=False))
        else:
            import uvicorn
            uvicorn.run(create_demo_app(args.directory), host="127.0.0.1", port=args.port)
        return 0
    except (ValueError, GTFSError, WalkingError) as error:
        print(f"Demo: {error}", file=sys.stderr)
        return 1
    except (OSError, KeyError, sqlite3.Error):
        print("Nie udało się przygotować lub uruchomić demo. Sprawdź lokalne oficjalne importy z 13.11.2026, zapisane cztery trasy ORS i nowy katalog wyjściowy; istniejące bazy zachowano.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
