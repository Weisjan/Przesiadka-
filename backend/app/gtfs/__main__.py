import argparse
import json
import sys
from pathlib import Path

from .archive import download_feed
from .importer import import_feed
from .sources import GTFSError, SOURCES, configured_path, source_for


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Jawny lokalny import statycznego GTFS. Nie pobiera danych realtime.")
    parser.add_argument("operator", choices=tuple(SOURCES))
    parser.add_argument("--archive", type=Path, help="Import istniejącego lokalnego ZIP zamiast pobierania.")
    parser.add_argument("--database", type=Path, default=configured_path(), help="Osobna baza GTFS; nie baza scenariuszy.")
    args = parser.parse_args(argv)
    try:
        path, provenance = (args.archive, None) if args.archive else download_feed(source_for(args.operator))
        metadata = import_feed(args.operator, path, args.database, provenance)
        print(json.dumps(metadata, ensure_ascii=False, indent=2))
        return 0
    except (GTFSError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
