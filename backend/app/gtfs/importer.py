import json
import math
import re
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .archive import archive_manifest, archive_sha256, csv_rows
from .schedule import WEEKDAYS, gtfs_date, gtfs_seconds
from .sources import GTFSError, namespaced, source_for
from .store import normalize_search, write_connection

MAX_METADATA_BYTES = 1024 * 1024

def integer(value: str, default: int | None = None, maximum: int = 2**31 - 1) -> int:
    if value == "" and default is not None:
        return default
    if not re.fullmatch(r"[0-9]{1,10}", value) or int(value) > maximum:
        raise GTFSError(f"Nieprawidłowa nieujemna liczba całkowita: {value!r}.")
    return int(value)


def coordinate(value: str, bound: int) -> float | None:
    if not value:
        return None
    try:
        result = float(value)
    except ValueError as error:
        raise GTFSError("Nieprawidłowa współrzędna przystanku.") from error
    if not math.isfinite(result) or not -bound <= result <= bound:
        raise GTFSError("Współrzędna przystanku poza zakresem.")
    return result


def insert_rows(connection: sqlite3.Connection, sql: str, rows) -> int:
    batch = []
    count = 0
    for row in rows:
        batch.append(row)
        count += 1
        if len(batch) == 2000:
            connection.executemany(sql, batch)
            batch.clear()
    if batch:
        connection.executemany(sql, batch)
    return count


def import_feed(operator: str, archive_path: Path, database: Path, provenance: dict | None = None) -> dict:
    source = source_for(operator)
    manifest = archive_manifest(archive_path)
    files = {item["name"] for item in manifest}
    metadata = {**source.metadata(), "is_realtime": False, "import_method": "local_archive",
                "downloaded_at": None, "last_modified": None, "production_date": None,
                **(provenance or {}), "imported_at": datetime.now(timezone.utc).isoformat(),
                "sha256": archive_sha256(archive_path), "files": manifest,
                "timezone": "Europe/Warsaw", "row_counts": {}}
    prefix = lambda value: namespaced(operator, value)
    counts = metadata["row_counts"]
    connection = write_connection(database)
    current_file = "agency.txt"
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("PRAGMA defer_foreign_keys=ON")
        connection.execute("DELETE FROM gtfs_sources WHERE operator=?", (operator,))
        connection.execute("INSERT INTO gtfs_sources VALUES (?,?)", (operator, "{}"))
        with zipfile.ZipFile(archive_path) as archive:
            with csv_rows(archive, "agency.txt", {"agency_name", "agency_url", "agency_timezone"}) as rows:
                agencies = []
                for row in rows:
                    if len(agencies) >= 1000 or row["agency_timezone"] != "Europe/Warsaw" or not row["agency_name"].strip():
                        raise GTFSError("Nieobsługiwana liczba agencji, nazwa lub strefa inna niż Europe/Warsaw.")
                    agencies.append((prefix(row.get("agency_id") or "__default__"), operator,
                                     row["agency_name"], row["agency_url"], row["agency_timezone"]))
                if not agencies:
                    raise GTFSError("Feed nie zawiera agencji.")
                counts["agency.txt"] = insert_rows(connection, "INSERT INTO gtfs_agencies VALUES (?,?,?,?,?)", agencies)
            current_file = "stops.txt"
            with csv_rows(archive, current_file, {"stop_id"}) as rows:
                def stops():
                    for row in rows:
                        location = integer(row.get("location_type", ""), 0, 4)
                        latitude = coordinate(row.get("stop_lat", ""), 90)
                        longitude = coordinate(row.get("stop_lon", ""), 180)
                        name = row.get("stop_name", "")
                        if location in (0, 1, 2) and (latitude is None or longitude is None or not name.strip()):
                            raise GTFSError("Przystanek, stacja lub wejście musi mieć nazwę i współrzędne.")
                        parent = row.get("parent_station")
                        yield (prefix(row["stop_id"]), operator, row["stop_id"], name, normalize_search(name),
                               latitude, longitude, row.get("stop_code", ""), location, prefix(parent) if parent else None)
                counts[current_file] = insert_rows(connection, "INSERT INTO gtfs_stops VALUES (?,?,?,?,?,?,?,?,?,?)", stops())
            if "calendar.txt" in files:
                current_file = "calendar.txt"
                with csv_rows(archive, current_file, {"service_id", "start_date", "end_date", *WEEKDAYS}) as rows:
                    def calendars():
                        for row in rows:
                            if any(row[day] not in ("0", "1") for day in WEEKDAYS):
                                raise GTFSError("Dni kalendarza muszą mieć wartości 0 lub 1.")
                            start, end = gtfs_date(row["start_date"]), gtfs_date(row["end_date"])
                            if start > end:
                                raise GTFSError("Początek kalendarza jest późniejszy niż koniec.")
                            days = sum((1 << index) for index, name in enumerate(WEEKDAYS) if row[name] == "1")
                            yield prefix(row["service_id"]), operator, days, start, end
                    counts[current_file] = insert_rows(connection, "INSERT INTO gtfs_services VALUES (?,?,?,?,?)", calendars())
            if "calendar_dates.txt" in files:
                current_file = "calendar_dates.txt"
                with csv_rows(archive, current_file, {"service_id", "date", "exception_type"}) as rows:
                    def exceptions():
                        for row in rows:
                            service = prefix(row["service_id"])
                            connection.execute("INSERT INTO gtfs_services(id,operator) VALUES (?,?) ON CONFLICT(id) DO NOTHING", (service, operator))
                            kind = integer(row["exception_type"], maximum=2)
                            if kind not in (1, 2):
                                raise GTFSError("Typ wyjątku kalendarza musi być równy 1 lub 2.")
                            yield service, gtfs_date(row["date"]), kind
                    counts[current_file] = insert_rows(connection, "INSERT INTO gtfs_exceptions VALUES (?,?,?)", exceptions())
            current_file = "routes.txt"
            with csv_rows(archive, current_file, {"route_id", "route_type"}) as rows:
                def routes():
                    for row in rows:
                        agency = row.get("agency_id")
                        if not agency and len(agencies) != 1:
                            raise GTFSError("Brak agency_id przy wielu agencjach.")
                        if not (row.get("route_short_name") or row.get("route_long_name")):
                            raise GTFSError("Trasa musi mieć krótką lub pełną nazwę.")
                        yield (prefix(row["route_id"]), operator, prefix(agency) if agency else agencies[0][0],
                               row.get("route_short_name", ""), row.get("route_long_name", ""), integer(row["route_type"]))
                counts[current_file] = insert_rows(connection, "INSERT INTO gtfs_routes VALUES (?,?,?,?,?,?)", routes())
            current_file = "trips.txt"
            with csv_rows(archive, current_file, {"trip_id", "route_id", "service_id"}) as rows:
                def trips():
                    for row in rows:
                        direction = row.get("direction_id", "")
                        yield (prefix(row["trip_id"]), operator, prefix(row["route_id"]), prefix(row["service_id"]),
                               row.get("trip_headsign", ""), integer(direction, maximum=1) if direction else None,
                               row.get("trip_short_name", ""), prefix(row["block_id"]) if row.get("block_id") else None,
                               prefix(row["shape_id"]) if row.get("shape_id") else None)
                counts[current_file] = insert_rows(connection, "INSERT INTO gtfs_trips VALUES (?,?,?,?,?,?,?,?,?)", trips())
            current_file = "stop_times.txt"
            with csv_rows(archive, current_file, {"trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time"}) as rows:
                def stop_times():
                    for row in rows:
                        arrival, departure = gtfs_seconds(row["arrival_time"]), gtfs_seconds(row["departure_time"])
                        if arrival is not None and departure is not None and arrival > departure:
                            raise GTFSError("Przyjazd na przystanek jest późniejszy niż odjazd.")
                        yield (prefix(row["trip_id"]), prefix(row["stop_id"]), integer(row["stop_sequence"]),
                               arrival, departure, row["arrival_time"], row["departure_time"], row.get("stop_headsign", ""),
                               integer(row.get("pickup_type", ""), 0, 3), integer(row.get("drop_off_type", ""), 0, 3))
                counts[current_file] = insert_rows(connection, "INSERT INTO gtfs_stop_times VALUES (?,?,?,?,?,?,?,?,?,?)", stop_times())
            for optional in ("feed_info.txt", "attributions.txt", "frequencies.txt"):
                if optional in files:
                    current_file = optional
                    if archive.getinfo(optional).file_size > MAX_METADATA_BYTES:
                        raise GTFSError("Przekroczono limit rozmiaru metadanych GTFS.")
                    with csv_rows(archive, optional, set()) as rows:
                        values = []
                        for row in rows:
                            if optional == "frequencies.txt":
                                raise GTFSError("Rozkłady częstotliwościowe frequencies.txt nie są jeszcze obsługiwane.")
                            if len(values) >= 1000:
                                raise GTFSError("Przekroczono limit metadanych GTFS.")
                            if optional == "attributions.txt":
                                for field in ("attribution_id", "agency_id", "route_id", "trip_id"):
                                    if row.get(field):
                                        row[field] = prefix(row[field])
                            values.append(row)
                        metadata[optional.removesuffix(".txt")] = values
                        counts[optional] = len(values)
        if any(counts.get(name, 0) == 0 for name in ("stops.txt", "routes.txt", "trips.txt", "stop_times.txt")):
            raise GTFSError("Wymagane pliki rozkładu są puste.")
        current_file = "relacje GTFS"
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise GTFSError("GTFS odwołuje się do brakującego przystanku, trasy, kursu, agencji lub kalendarza.")
        invalid = connection.execute("""
            SELECT 1 FROM (
              SELECT arrival_seconds,departure_seconds,MAX(COALESCE(departure_seconds,arrival_seconds)) OVER (
                PARTITION BY trip_id ORDER BY stop_sequence ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS previous
              FROM gtfs_stop_times st JOIN gtfs_trips t ON t.id=st.trip_id WHERE t.operator=?
            ) WHERE COALESCE(arrival_seconds,departure_seconds)<previous LIMIT 1
        """, (operator,)).fetchone()
        if invalid:
            raise GTFSError("Czasy kursu cofają się między kolejnymi przystankami.")
        bounds = connection.execute("""
            SELECT MIN(day),MAX(day) FROM (
              SELECT start_date AS day FROM gtfs_services WHERE operator=?
              UNION ALL SELECT end_date FROM gtfs_services WHERE operator=?
              UNION ALL SELECT e.date FROM gtfs_exceptions e JOIN gtfs_services s ON s.id=e.service_id WHERE s.operator=?)
        """, (operator, operator, operator)).fetchone()
        if bounds[0] is None:
            raise GTFSError("Kalendarz nie zawiera dat kursowania.")
        metadata.update({"service_start_date": bounds[0], "service_end_date": bounds[1],
                         "max_departure_seconds": connection.execute("SELECT COALESCE(MAX(departure_seconds),0) FROM gtfs_stop_times st JOIN gtfs_trips t ON t.id=st.trip_id WHERE t.operator=?", (operator,)).fetchone()[0],
                         "missing_departure_times": connection.execute("SELECT COUNT(*) FROM gtfs_stop_times st JOIN gtfs_trips t ON t.id=st.trip_id WHERE t.operator=? AND departure_seconds IS NULL", (operator,)).fetchone()[0],
                         "ignored_files": sorted(files - set(counts))})
        connection.execute("UPDATE gtfs_sources SET metadata=? WHERE operator=?", (json.dumps(metadata, ensure_ascii=False), operator))
        connection.commit()
        return metadata
    except (sqlite3.Error, GTFSError, UnicodeError, zipfile.BadZipFile) as error:
        connection.rollback()
        raise GTFSError(f"Import {operator}, {current_file}: {error}. Poprzedni import pozostaje bez zmian.") from error
    finally:
        connection.close()
