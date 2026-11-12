# Static GTFS integration

This backend extension imports official timetable ZIP files explicitly. It does not fetch feeds during FastAPI startup or API requests, provide realtime information, or change the transfer evaluation algorithm. The frontend still uses saved scenarios and the three fictional demos.

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

## Read-only API

Start the backend with the existing README command. No import occurs on startup.

| Endpoint | Meaning |
| --- | --- |
| `GET /api/transit/sources` | Both configured providers, import availability, provenance, attribution and service-date bounds. Works before the first import. |
| `GET /api/transit/stops?query=glowny&limit=50` | Accent-insensitive substring search, keeping each provider's stops separate. Default limit 50, maximum 100. |
| `GET /api/transit/departures?stop_id=skm:7500&date=2026-11-11&limit=50` | Planned departures on the given civil date. Default limit 50, maximum 200; `has_more` reports truncation. |

All envelopes contain `is_realtime: false`. Stops/departures return 503 if the transit database is absent or invalid, unknown stops return 404, and invalid query parameters return 422. The OpenAPI schema describes the query parameters. No transit write/import endpoint is exposed.

Example **departure item** observed in the real SKM import on 2026-11-11 (excerpt, not realtime):

```json
{
  "operator": "skm",
  "stop_id": "skm:7500",
  "stop_name": "GDAŃSK GŁÓWNY",
  "route_id": "skm:285219",
  "line": "SKM",
  "direction": "Gdynia Cisowa",
  "trip_id": "skm:285219",
  "service_id": "skm:285219",
  "service_date": "2026-11-11",
  "gtfs_departure_time": "00:04:00",
  "departure_at": "2026-11-11T00:04:00+01:00"
}
```

The same query also returned a `24:15:00` departure belonging to service date **2026-11-10**, exposed as `2026-11-11T00:15:00+01:00`. ZTM stop `ztm:2001` returned line `6` toward `Jelitkowo` at `2026-11-11T04:57:00+01:00`. These IDs/times can change on the next import.

## Safety limits and unsupported data

- Download: 30-second network timeout, 80 MiB maximum, and a 180-second elapsed budget checked between reads. Only the fixed official source URLs are used; HTTPS is required after redirects. Failed downloads leave the cached archive intact.
- ZIP: at most 64 root-level members, 512 MiB expanded total, 256 MiB per member, compression ratio at most 200, central directory at most 1 MiB. Stored/deflate compression only. Paths, links, duplicate names, encrypted entries, ZIP64 and multipart archives are rejected. Files are streamed, never extracted to disk.
- CSV: strict UTF-8/UTF-8 BOM and header/column checks; at most 4 million rows per file, 128 columns and 1,048,576 characters per physical line. Optional metadata files are limited to 1 MiB. IDs, coordinates, times, calendar values, foreign keys and trip chronology are validated.
- Extended times through `167:59:59` are supported. Frequency-based schedules with nonempty `frequencies.txt` are rejected rather than presented as exact departures. Missing departure times are counted and omitted, without interpolation. Pickup type 1 is excluded; types 2/3 are returned as provided and may require prior arrangements.
- Optional files outside the imported model are listed in `ignored_files`. The importer is not a full GTFS validator or journey planner. No automatic cross-provider walking links, live feeds, frontend schedule picker, refresh job or schema migrations are included.

## Verification

Use the backend and frontend test commands in [README](../README.md#testing). Tests use tiny generated local ZIP fixtures, never download live feeds, and isolate SQLite files. They cover calendar variants, weekdays/exceptions, 24+/29-hour times, midnight/DST, namespace collisions, rollback, invalid ZIPs, network failures, limits, query validation and read-only behavior. Real-feed imports are a separate manual smoke check, not a network-dependent unit test.

## First interchange search

This backend-only feature covers **Gdańsk Główny SKM → Dworzec Główny 01 ZTM**. It does not change saved scenarios, demos or the frontend. It neither downloads data nor writes to either database.

### Stop audit and walking assumption

The local snapshots described above were inspected again on **12 November 2026**. SKM contains `skm:7500` (`GDAŃSK GŁÓWNY`, 54.3565922, 18.6443487), with `location_type=0` and no `parent_station`. It does **not** distinguish physical platforms. The import must not be presented as platform-level information.

ZTM has twelve separate records, all with `location_type=0` and no `parent_station`:

| Namespaced stop ID | Name |
| --- | --- |
| `ztm:1013` | Dworzec Główny 18 |
| `ztm:1014` | Dworzec Główny 05 |
| `ztm:1015` | Dworzec Główny 14 |
| `ztm:1016` | Dworzec Główny 07 |
| `ztm:1017` | Dworzec Główny 12 |
| `ztm:1019` | Dworzec Główny 10 |
| `ztm:1020` | Dworzec Główny 11 |
| `ztm:1021` | Dworzec Główny 08 |
| `ztm:1022` | Dworzec Główny 13 |
| `ztm:1023` | Dworzec Główny 06 |
| `ztm:2001` | Dworzec Główny 01 |
| `ztm:2002` | Dworzec Główny 02 |

The immutable `TransferLink` in `transfer_search.py` explicitly selects **`skm:7500 → ztm:2001`**, ID `gdansk-glowny-skm-ztm-01`. ZTM stop 01 is at 54.355509269859, 18.645663339105. Neither names nor coordinate distances create links; parents and nearby stops are never expanded automatically. Missing stops or a changed `location_type` invalidate the link. Revalidate the pairing when feed identifiers change.

No measured or authoritative walking-time evidence is available. `walking_minutes` is mandatory in every search, with `walking_time_source="estimated"` and `walking_time_basis="user_input"`. The API cannot promote this to `verified`. The example value of 5 minutes below is an assumption, not a recommendation or accessibility guarantee. Access paths, crossings and the actual SKM platform need separate verification.

Stop 01 serves different routes and variants. For example, route `ztm:6`, `direction_id=0`, has headsigns `Jelitkowo` and `Strzyża PKM` in the snapshot; `ztm:12` has `Strzyża PKM`, `Wilka-Krzyżanowskiego` and `Zaspa`. SKM direction IDs are absent; the arriving course is selected explicitly by trip ID and service date, retaining the supplied headsign.

### Contract

- `GET /api/transit/transfer-links`: describe the one configured pair, both stop records and the walking assumption. Returns 409 if imported stops cannot support it, 503 if the database is unavailable.
- `POST /api/transit/transfers/search`: read-only search and evaluation. The JSON fields are documented below and in `/openapi.json`.

| Input | Meaning and bounds |
| --- | --- |
| `link_id` | Required explicit pair ID. Other pairs return 404. |
| `arrival_trip_id` | Required namespaced SKM trip ID, not a line name. |
| `arrival_service_date` | Required ISO date `YYYY-MM-DD`: **day of service**, not necessarily the civil arrival date. |
| `arrival_stop_sequence` | Optional exact occurrence if a trip visits `skm:7500` more than once; otherwise ambiguity returns 409. |
| `departure_route_id` | Required namespaced ZTM route ID, not its display name. |
| `departure_trip_id` | Optional reference trip selecting a downstream variant. This chooses a pattern, not the reference trip's service date. |
| `walking_minutes` | Required integer 0–180; estimated by the caller. |
| `delay_minutes` | Simulated delay 0–180, finite; default 0. No realtime delay is read. |
| `window_minutes` | Elapsed search interval from the **scheduled SKM arrival**, 1–360 minutes; default 120. End is exclusive. |
| `limit` | Number of evaluations returned, 1–10; default 5. `has_more` reports additional matching departures. |

Candidates are sorted by actual instant starting at the scheduled arrival, **without shifting the search by the simulated delay**. A candidate can therefore already be unreachable at zero delay; inspect `evaluation.status` and `has_safe_margin`. `outcome="evaluated"` means evaluations were produced, not that all transfers are reachable. `outcome="no_departures"` means no usable departure of the selected variant exists in this window, not that the entire network has no service.

Both feeds, calendars and stop patterns are read in one SQLite read-only transaction. The incoming trip's calendar is checked on its service date; its `arrival_time`, not its departure time, feeds the existing pure `evaluate_transfer` function. Outgoing candidates reuse the same UTC/calendar query as `/departures`, retaining their own `service_date`, raw extended GTFS time and offset-aware timestamp. GTFS noon-minus-12-hours conversion, midnight and DST semantics remain unchanged.

Plan B uses the **same stop, exact route ID, direction ID, effective headsign and ordered downstream sequence of stop IDs with pickup/drop-off restrictions**. Shape geometry is not imported; matching does not claim geometric path identity. Upstream differences before the boarding stop are irrelevant to this conservative downstream match. Multiple directions or downstream patterns return 409 `ambiguous_departure_variant` with reference-trip choices (up to 20, with `has_more_choices`). Resubmit with a chosen `departure_trip_id`. This deliberately rejects some potentially usable variants rather than guessing. Multiple indistinguishable Plan B courses at the same instant return 409 `ambiguous_plan_b`, exposing their IDs instead of choosing one arbitrarily.

Only unconditional boarding/alighting (`pickup_type=0` / incoming `drop_off_type=0`) is supported. Missing arrival times, terminal-only boarding and reserved/on-request services are not treated as ordinary transfers. More than 2,000 candidate departures or 1,000 downstream stop records returns a readable 409 instead of truncating analysis. The result limit does not truncate the courses inspected for Plan B.

404 identifies unknown links, arriving trips or routes. 422 identifies invalid inputs, inactive incoming services, unusable arrivals or dates outside feed bounds. In particular, the SKM service date and the **entire outgoing civil-date window** must fit their respective imported service-date bounds. The latter is conservative: even a known 24+ departure beyond the final ZTM service date cannot establish full search coverage, so this search rejects that boundary window. The existing `/departures` endpoint can still expose such spillover departures. Dates inside the bounds can legitimately have no courses. Historical queries are allowed; being inside calendar bounds is not a guarantee that the latest publication was imported. Source timestamps and hashes remain visible for freshness checks.

Plan B is bounded by the search window. `unavailable` means no matching reachable later course **within that window**, never a claim that no later service exists anywhere. `sources` retains the existing attribution, official URLs, import/download timestamps, calendar bounds and hashes. All responses are `is_realtime=false` with `schedule_status="planned"` on evaluations.

### Real local HTTP example

Observed using the existing local imports on **12 November 2026**, via a temporary Uvicorn server and real HTTP requests; no fresh download was performed. After starting the normal backend, use PowerShell:

```powershell
$body = @{
    link_id = "gdansk-glowny-skm-ztm-01"
    arrival_trip_id = "skm:284778"
    arrival_service_date = "2026-11-12"
    departure_route_id = "ztm:6"
    walking_minutes = 5
    delay_minutes = 10
    limit = 2
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/transit/transfers/search" -ContentType "application/json" -Body $body
```

IDs and availability can change after reimport. The SKM arrival is `skm:284778`, service/route ID `skm:284778`, stop sequence 27, at `2026-11-12T17:32:00+01:00`, toward Gdańsk Śródmieście. The response includes an earlier, already unreachable departure at 17:35. The **second result** (excerpt) is:

```json
{
  "departure": {
    "operator": "ztm",
    "stop_id": "ztm:2001",
    "route_id": "ztm:6",
    "trip_id": "ztm:6202611121723_21_006-01",
    "service_id": "ztm:220261112",
    "service_date": "2026-11-12",
    "direction_id": 0,
    "direction": "Jelitkowo",
    "departure_at": "2026-11-12T17:45:00+01:00"
  },
  "evaluation": {
    "margin_minutes": -2.0,
    "delay_threshold_minutes": 8.0,
    "status": "Nie zdążysz",
    "has_safe_margin": true,
    "expected_stop_arrival_at": "2026-11-12T17:47:00+01:00",
    "plan_b_status": "available",
    "plan_b_departure_at": "2026-11-12T17:55:00+01:00"
  },
  "plan_b": {
    "operator": "ztm",
    "route_id": "ztm:6",
    "trip_id": "ztm:6202611121733_21_006-02",
    "service_date": "2026-11-12",
    "direction": "Jelitkowo",
    "departure_at": "2026-11-12T17:55:00+01:00"
  }
}
```

For this same second result, delay 0 gives +8 minutes / `Zdążysz`; delay 8 gives zero / `Na styk`; delay 10 gives −2 / `Nie zdążysz` and the Plan B above. Neither reachable result requires Plan B. The real HTTP checks also confirmed 422 outside calendar bounds, 404 for an unknown link and unchanged SHA-256 hashes of both existing databases.

Fixture tests cover these boundaries plus calendar-only/dates-only data, exceptions, weekends, 24+/25+ times, spring/fall DST, exact stop occurrences, route/direction/downstream/platform separation, missing data, no later course, bounded searches and no writes or network calls. Run the full regression using the README commands.

Next step: measure and document the walking path from actual SKM platforms to ZTM stop 01 before labeling any walking time as verified or exposing the connection as platform-accurate.
