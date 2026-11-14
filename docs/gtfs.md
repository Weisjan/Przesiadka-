# Static GTFS integration

The current four-pair registry, approval audit and extended API contract are documented in [approved transfer links](transfer-links.md). Search uses exact selected courses and cached walking time. `/journeys` accepts `link_id`, defaulting to the original pair. The frontend accepts an SKM train and a ZTM goal. `/transfers/suggest` ranks matching courses across approved boarding stops.

This extension imports official timetable ZIP files explicitly. It does not fetch feeds during FastAPI startup or API requests, provide realtime information, or change the transfer evaluation algorithm. The screen selects actual courses for approved links.

## Sources and reuse conditions

Verified on **11 November 2026**:

| Provider | Official feed | Documentation and terms |
| --- | --- | --- |
| Zarząd Transportu Miejskiego w Gdańsku | [GTFS ZIP](https://ckan.multimediagdansk.pl/dataset/c24aa637-3619-4dc2-a171-a23eec8f2172/resource/30e783e4-2bec-4a7d-bb22-ee3e3b26ca96/download/gtfsgoogle.zip) | [Dataset](https://ckan.multimediagdansk.pl/pl/dataset/tristar), [reuse terms, updated 2024-01-08](https://ckan.multimediagdansk.pl/dataset/c24aa637-3619-4dc2-a171-a23eec8f2172/resource/09cafa1b-604b-4408-ac48-5720319b72b7/download/regulamin-korzystania-z-danych.pdf) |
| PKP Szybka Kolej Miejska w Trójmieście Sp. z o.o. | [GTFS ZIP](https://www.skm.pkp.pl/gtfs-mi-kpd.zip) | [Timetable BIP](https://bip.skm.pkp.pl/c60/rozklad-jazdy), [reuse terms](https://bip.skm.pkp.pl/otwarte-dane) |

Both providers permit public-sector information reuse subject to their published conditions. Attribute the provider by its full name, link to its repository where possible, and give the production and acquisition dates. Both require attention to data freshness. ZTM's CKAN metadata also labels the dataset **Creative Commons Attribution**, without specifying a version; do not infer a CC version or apply this label to SKM.

SKM states that the file is refreshed daily and recommends fetching it no earlier than **04:00**. There is no automatic refresh in this project.

`GET /api/transit/sources` carries the attribution, source and terms URLs, download/import timestamps, HTTP `Last-Modified`, archive SHA-256, ZIP member timestamps and calendar bounds. A local-file import is explicitly marked `local_archive`, with no invented download timestamp.

**Production-date limitation:** neither inspected feed explicitly provides a creation timestamp. `production_date` is therefore `null`. HTTP modification times, ZIP timestamps and calendar validity are retained separately; none is silently relabeled as creation time. Confirm the production date with the publisher before public redistribution and retain the required attribution. This change keeps downloaded data local and out of Git.

## Observed archive structure

These are inspected snapshots, not promises about future releases or guaranteed service on every date:

| Property | ZTM | SKM |
| --- | --- | --- |
| Downloaded ZIP bytes | 27,057,210 | 15,258,598 |
| `calendar.txt` | Absent | Present: 1,454 rows |
| `calendar_dates.txt` | Present: 60 rows; all service dates come from this file | Present: 10,481 rows; overrides the base calendar |
| Service-date bounds | 2026-11-11 through 2026-11-25 | 2026-10-19 through 2026-12-12 |
| Stops / routes / trips | 1,625 / 93 / 92,600 | 81 / 1,454 / 1,454 |
| Stop-time rows | 2,212,094 | 38,875 |
| Largest departure time | 29:25:00 | 24:51:00 |
| Agency timezone | Europe/Warsaw | Europe/Warsaw |

ZTM contains `agency.txt`, `calendar_dates.txt`, `feed_info.txt`, `routes.txt`, `shapes.txt`, `stop_times.txt`, `stops.txt` and `trips.txt`. SKM contains the same core timetable files, with `calendar.txt` instead of `feed_info.txt`. Both have eight root-level files, valid UTF-8 CSV, and no `frequencies.txt` in these snapshots. `shapes.txt` is checked for ZIP integrity but is not loaded into the database.

Calendar bounds are service dates. Departures above 24:00 can fall on a later civil date, beyond the last service date. ZTM's `feed_info.txt` has an empty `feed_start_date` and `feed_end_date=20261125`; the reported start comes from its service calendar, not an invented feed-info value.

## Import commands

From the repository root, in PowerShell:

```powershell
Set-Location .\backend
uv run python -m app.gtfs ztm
uv run python -m app.gtfs skm
```

Run these sequentially. Each command downloads the configured official URL, validates the archive and imports only that operator. Successful imports print JSON metadata; failures write a readable error to stderr and exit with status 1. Network errors never select an alternative feed automatically.

Default files are under ignored `backend/data/gtfs/`: `ztm.zip`, `skm.zip` and `transit.db`. The database is separate from `backend/data/scenarios.db`. Existing non-GTFS SQLite databases are rejected before schema changes; never point the importer at the scenario database.

To reuse a local archive, without network access:

```powershell
uv run python -m app.gtfs ztm --archive .\data\gtfs\ztm.zip
```

For a different transit database, set `$env:PRZESIADKA_TRANSIT_PATH` in both the CLI and API terminals. The CLI also accepts `--database`. Keep the API path and importer path consistent. Keep downloaded archives and databases in ignored locations.

## Model and transaction boundary

The implementation uses the Python standard library (`urllib`, `zipfile`, `csv`, `sqlite3`, `zoneinfo`) and existing FastAPI dependencies. No additional packages are required.

- `sources.py`: official URLs, attribution and local path configuration.
- `archive.py`: bounded download, ZIP/CRC checks and strict UTF-8 CSV streaming with optional BOM.
- `importer.py` and `store.py`: normalized tables for sources, agencies, stops, routes, trips, services, calendar exceptions and stop times. Inserts use batches of 2,000 rows.
- `schedule.py`: GTFS dates, extended hours and conversion to Warsaw instants.
- `api.py` and `__main__.py`: read-only endpoints and explicit CLI.

Every persistent identifier and reference is namespaced: `ztm:2001`, `skm:7500`, `ztm:<trip_id>`, `skm:<service_id>`, and so on. The original stop ID is retained as `source_stop_id`. Stops are never merged by name or proximity. Shape and block references are namespaced, but shape geometry and block operations are not implemented.

Each operator replacement uses one SQLite transaction. Validation or referential failures roll back the replacement; the other operator remains intact. The transit database has a dedicated SQLite application ID and schema version. API connections open it in read-only mode and never initialize it.

## Time and calendar semantics

The importer supports `calendar.txt`, `calendar_dates.txt`, or both. Added/removed dates override weekday flags. Times are stored as elapsed seconds plus the original GTFS strings; they are not reduced modulo 24 hours.

Following the [GTFS Schedule reference](https://gtfs.org/documentation/schedule/reference/), an instant is computed from local noon on the **service date**, converted to UTC, minus 12 elapsed hours, plus the GTFS time. This matters on DST days: treating every GTFS time as a naive wall-clock time would give different results. Responses use ISO 8601 offsets valid for `Europe/Warsaw`.

The departure query uses a **civil Warsaw date**, not a service date. It checks surrounding service days so that 24:xx/25:xx departures and DST boundary spillovers are included once, ordered by UTC instant. `service_date` and `gtfs_departure_time` remain visible in each result.

## Screen API

The current course-selection and evaluation API is documented in [approved links](transfer-links.md) and the root README. Provider metadata remains available through /api/transit/sources.

## Safety limits and unsupported data

- Download: 30-second network timeout, 80 MiB maximum, and a 180-second elapsed budget checked between reads. Only the fixed official source URLs are used; HTTPS is required after redirects. Failed downloads leave the cached archive intact.
- ZIP: at most 64 root-level members, 512 MiB expanded total, 256 MiB per member, compression ratio at most 200, central directory at most 1 MiB. Stored/deflate compression only. Paths, links, duplicate names, encrypted entries, ZIP64 and multipart archives are rejected. Files are streamed, never extracted to disk.
- CSV: strict UTF-8/UTF-8 BOM and header/column checks; at most 4 million rows per file, 128 columns and 1,048,576 characters per physical line. Optional metadata files are limited to 1 MiB. IDs, coordinates, times, calendar values, foreign keys and trip chronology are validated.
- Extended times through `167:59:59` are supported. Frequency-based schedules with nonempty `frequencies.txt` are rejected rather than presented as exact departures. Missing departure times are counted and omitted, without interpolation. Pickup type 1 is excluded; types 2/3 are returned as provided and may require prior arrangements.
- Optional files outside the imported model are listed in `ignored_files`. The importer is not a full GTFS validator or network-wide journey planner. No automatic cross-provider walking links, live feeds, refresh job or schema migrations are included. The frontend picker uses the approved-link registry.

## Verification

Use the backend and frontend test commands in [README](../README.md#testing). Tests use tiny generated local ZIP fixtures, never download live feeds, and isolate SQLite files. They cover calendar variants, weekdays/exceptions, 24+/29-hour times, midnight/DST, namespace collisions, rollback, invalid ZIPs, network failures, limits, query validation and read-only behavior. Real-feed imports are a separate manual smoke check, not a network-dependent unit test.
