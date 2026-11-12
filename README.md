# Przesiadka+

A local MVP for checking whether a public transport transfer in Gdańsk remains reachable when the arriving service is delayed. It compares scheduled times, walking time and a simulated delay, then identifies a later departure when the original connection is missed.

The interface is in Polish. Dark Transit uses two journey cards, large scheduled times and an animated SVG figure. Transfer details include a timeline and Plan B.

The main **Rozkłady** view selects real journeys from locally imported GTFS data for one explicit pair: SKM Gdańsk Główny → ZTM Dworzec Główny 01. Choose the arriving and departing courses. Walking time can come from a saved OpenRouteService estimate or your own manual input. No verified realtime source is connected; delay starts at zero and remains an explicitly labeled simulation.

## Demo

Start both services, open **Scenariusze** and choose an example under **Wypróbuj przykład**. Move the delay slider to update the margin, status, timeline and Plan B. These examples remain separate from the real GTFS view and from saved scenarios.

| Example | Schedule | Try |
| --- | --- | --- |
| **Spokojna przesiadka** | Arrival 17:42, departure 17:51, walking 3 min, next departure 18:03 | Delays of 0, 6 and 8 min give margins of +6, 0 and −2 min. At 8 min, Plan B is 18:03. |
| **Przesiadka na styk** | Arrival 17:48, departure 17:52, walking 3 min, next departure 18:04 | Delays of 0, 1 and 2 min show a reachable, just-in-time and missed connection. |
| **Ostatni kurs** | Arrival 23:58, departure 00:04 the following day, walking 3 min, no later departure | A 4 min delay misses the connection and leaves no alternative. |

These are **fictional demonstration scenarios**, fixed to 10–11 November 2026 in `Europe/Warsaw`. They are not current transport timetables. Examples use the real evaluation API without being saved to SQLite. **Wróć do swoich scenariuszy** returns to the previously selected saved scenario.

### Screenshots

Real browser captures from the local GTFS import, for service date **12 November 2026**. Walking time is a user-supplied estimate of 5 minutes. These captures show a fixed schedule snapshot, not live transport information.

| View | Capture |
| --- | --- |
| Desktop, 1440 px, zero margin at simulated delay +8 min | [Open screenshot](docs/screenshots/dark-transit-desktop.png) |
| Mobile, 390 px, the same transfer | [Open screenshot](docs/screenshots/dark-transit-mobile.png) |
| Missed connection at +10 min, with Plan B at 17:55 | [Open screenshot](docs/screenshots/dark-transit-plan-b.png) |

## Features

- Create, list, select, edit and delete scenarios, with deletion confirmation and persistent local storage.
- Enter dates through calendar controls and times as HH:MM, including an explicit choice for repeated DST hours.
- Simulate arrival delay and inspect the transfer margin and zero-delay threshold.
- Show reachable, just-in-time and missed states, with Plan B or an explicit unavailable state.
- Inspect timeline events for full dates and offsets; coincident events share one point, while nearby events remain distinct.
- Use the responsive interface with loading, empty and error states, keyboard controls and reduced-motion support.
- Explicitly import official static ZTM/SKM GTFS schedules and select real arrivals/departures through the read-only API. Select line, direction, date and an exact scheduled course without entering IDs or times.
- Evaluate imported SKM arrivals against ZTM departures for one explicit interchange: Gdańsk Główny SKM → Dworzec Główny 01 ZTM, with a user-estimated walking time and strict route-variant matching.

## Tech Stack

| Layer | Technologies |
| --- | --- |
| Backend | Python 3.13, FastAPI, Pydantic, SQLModel, SQLite, Uvicorn, `zoneinfo` and `tzdata` |
| Frontend | React 19, TypeScript, Vite, CSS Modules, native SVG and browser `Intl` APIs |
| Tooling and tests | uv with `uv.lock`; npm with `package-lock.json`; pytest, HTTPX/TestClient and Node's built-in test runner |

## Architecture

- [Transfer logic](backend/app/transfer_logic.py) is a pure function with no HTTP or database dependencies.
- [The FastAPI application](backend/app/main.py) registers CRUD and evaluation routes. SQLModel stores scenarios in `backend/data/scenarios.db`, created on startup. `PRZESIADKA_DATABASE_PATH` can override that location.
- [TransferAnalysis](frontend/src/TransferAnalysis.tsx) sends time inputs to `POST /api/transfers/evaluate`. The frontend presents the response rather than calculating transfer outcomes.
- [Transit](frontend/src/Transit.tsx) selects exact GTFS course occurrences, including service date and stop sequence, and calls the transfer search endpoint. The backend selects Plan B; React only presents the result. Manual delay survives retries and view changes, and resets to zero when a new course is chosen.
- [Demo examples](frontend/src/demoExamples.ts) contain fixed inputs without database identifiers. Selecting one reuses the analysis component and does not call the CRUD write endpoints.
- [GTFS integration](docs/gtfs.md) uses a separate local SQLite database and explicit CLI imports. Startup and API requests never download feeds; transfer evaluation remains independent.
- [Walking estimates](docs/walking.md) use an explicit ORS CLI and separate `backend/data/walking.db`. API reads use cached results; manual corrections take precedence. The key is only read from the CLI process environment.

### API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Return `{"status":"ok"}`. |
| GET | `/api/scenarios` | List saved scenarios. |
| GET | `/api/scenarios/{scenario_id}` | Read one scenario. |
| POST | `/api/scenarios` | Create a scenario; return HTTP 201. |
| PUT | `/api/scenarios/{scenario_id}` | Replace all editable scenario fields. |
| DELETE | `/api/scenarios/{scenario_id}` | Delete a scenario; return HTTP 204. |
| POST | `/api/transfers/evaluate` | Evaluate supplied times without reading or writing scenarios. |
| GET | `/api/transit/sources` | Report GTFS source/import metadata and attribution. |
| GET | `/api/transit/stops?query=...` | Search imported stops without merging operators. |
| GET | `/api/transit/departures?stop_id=...&date=...` | List planned departures on a civil Warsaw date. |
| GET | `/api/transit/journeys?leg=arrival&date=...` | List scheduled arrivals for the fixed SKM stop; `leg=departure` lists the fixed ZTM stop. Optional `after` bounds departures to six hours after an arriving instant. |
| GET | `/api/transit/transfer-links` | Describe the single explicit stop pair and unverified walking assumption. |
| GET | `/api/transit/walking-transfers?from_stop_id=...&to_stop_id=...` | Read a saved directional walking estimate, including freshness, source and attribution; never call ORS. |
| GET | `/api/transit/nearby-stops?stop_id=skm:7500&radius_m=500` | Discover opposite-operator geographic candidates and directional cache status; never call ORS or create transfer links. |
| POST | `/api/transit/transfers/search` | Search and evaluate planned transfers using an arriving trip's service date. |

Evaluation accepts `arrival_at`, `departure_at`, `walking_minutes`, `delay_minutes` and `next_departures`. The response includes the margin, delay threshold, status, expected arrival at the stop and Plan B state. Invalid inputs return HTTP 422; missing scenarios return HTTP 404.

## Getting Started

### Prerequisites

- Windows PowerShell with Python 3.13 and uv available on `PATH`.
- Node.js 24.x and npm. Frontend tests use Node's native TypeScript support.
- A modern browser and free local ports 8000 and 5173.

Run each block from the repository root in a separate PowerShell terminal. `npm.cmd` avoids PowerShell execution-policy issues with the npm script wrapper.

### Backend

```powershell
Set-Location .\backend
uv sync --locked
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The core application requires no manual database setup, accounts or API keys. The optional ORS walking import needs `ORS_API_KEY` in that CLI process. Saved scenarios remain in SQLite after the backend restarts.

### Frontend

```powershell
Set-Location .\frontend
npm.cmd ci
npm.cmd run dev
```

| Service | Address |
| --- | --- |
| Application | <http://127.0.0.1:5173> |
| API health | <http://127.0.0.1:8000/api/health> |
| OpenAPI schema | <http://127.0.0.1:8000/openapi.json> |

Swagger UI (`/docs`) and ReDoc (`/redoc`) are disabled. The OpenAPI JSON is the available API reference. Stop each service with `Ctrl+C`.

### Optional static GTFS import

From `backend/`, run these sequentially:

```powershell
uv run python -m app.gtfs ztm
uv run python -m app.gtfs skm
```

Archives and `transit.db` stay in ignored `backend/data/gtfs/`, separate from user scenarios. These are static schedules, not realtime feeds. See [GTFS documentation](docs/gtfs.md) for local-file imports, calendar semantics, limits and provider attribution, including the unresolved production-date metadata.

### Optional saved walking estimate

From `backend/`, preview the one supported pair without network access or writes:

```powershell
uv run python -m app.walking skm:7500 ztm:2001 --dry-run
```

With `ORS_API_KEY` already configured in the current terminal's environment, import explicitly:

```powershell
uv run python -m app.walking skm:7500 ztm:2001 --max-requests 1
```

Do not put the key in arguments, code, logs or Git. See [walking documentation](docs/walking.md) for secure prompting, cache/resume behavior, current CC BY-SA 4.0 attribution and limits. Automatic-fill tests use a clearly identified synthetic fixture. A later local read confirmed the previously imported real estimate; no provider request was made for that check.

[Nearby-stop discovery](docs/nearby.md) adds a separate candidate importer that defaults to dry-run:

```powershell
uv run --directory backend python -m app.walking.candidates skm:7500 --max-pairs 3 --max-requests 3
```

Run this block from the repository root. Execution requires `--execute`; request budgets include retries. Geographic candidates do not expand the current single-pair journey planner or UI.

## Testing

Run these blocks from the repository root after installing the existing dependencies.

Backend tests use isolated temporary SQLite databases. A unique temporary directory also avoids conflicts with earlier pytest runs:

```powershell
Set-Location .\backend
$testTemp = Join-Path $env:TEMP ("przesiadka-tests-" + [guid]::NewGuid().ToString())
uv run python -m pytest --basetemp $testTemp
```

Coverage includes CRUD, validation, persistence across application restarts, CORS, transfer boundaries, DST, midnight and evaluation without database access. Local GTFS fixtures also cover secure import, calendar variants, namespaces, rollback and read-only transit endpoints.

```powershell
Set-Location .\frontend
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
```

Frontend unit tests cover Warsaw time conversion, fixed demo inputs, timeline event grouping, close timestamps, exact GTFS course identity, response validation and readable API errors. The build script also runs the typecheck. There is no committed browser end-to-end suite. The screenshots above were captured during a separate Playwright/Edge smoke check against the local import and an isolated scenario database; that check is not part of `npm test`.

## Engineering Decisions

- **Time handling:** API inputs require full ISO 8601 dates with offsets valid for `Europe/Warsaw`. The form rejects nonexistent spring-transition times and asks which occurrence to use during the autumn overlap. SQLite stores ISO strings to preserve offsets.
- **Elapsed time:** the backend converts inputs to UTC before arithmetic and comparisons. Full dates handle midnight and DST without comparing clock times alone.
- **Transfer boundaries:** `margin = departure − (arrival + delay + walking)`. Positive means `Zdążysz`, zero means `Na styk`, and negative means `Nie zdążysz`. The threshold is the margin at zero delay; non-positive thresholds indicate no safe initial margin.
- **Plan B:** only a missed connection needs an alternative. The backend chooses the earliest supplied later departure at or after the expected arrival at the stop. Candidates must belong to the same departing line and direction; the application does not search a transport network.
- **Asynchronous UI:** analysis requests are debounced by 150 ms. Cleanup aborts superseded requests, and a disposal guard ignores late responses. Results are matched to the current scenario, delay and retry attempt.
- **GTFS selection:** civil picker dates are kept separate from each course's service date. Search identifies an exact departure by trip ID, service date and stop sequence. No frontend timetable arithmetic chooses an alternative. Structured 409/422 errors remain readable; changing a direction or date clears the modal's old selection.
- **Accessibility:** labeled native controls, modal focus handling, visible keyboard focus and live status text accompany the visual result. Color is not the only status cue. CSS respects `prefers-reduced-motion`.

## Limitations

- No live transport feeds, network-wide routing or verified walking paths. The GTFS search covers one explicit stop pair; all calculations depend on supplied schedules and walking times.
- Outcomes are deterministic time comparisons, not probability estimates or guarantees that a connection will be held.
- Local, unauthenticated MVP: no user accounts, access control or production deployment setup. The frontend API origin is fixed to `http://127.0.0.1:8000`; CORS allows only the two configured localhost origins on port 5173.
- SQLite tables are created automatically, but schema migrations are not implemented. Saved scenarios accept at most 100 strictly increasing later departures and an integer walking time from 0 to 1440 min.

## Future Improvements

Not implemented:

- Commit browser end-to-end tests and add CI checks.
- Add versioned database migrations and scenario import/export.
- Measure and document platform-specific walking paths before marking any walking time as verified.
- Add further explicit interchange pairs and investigate a separately validated realtime source with reliable trip matching.
