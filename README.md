# Przesiadka+

A local MVP for checking whether a public transport transfer in Gdańsk remains reachable when the arriving service is delayed. It compares scheduled times, walking time and a simulated delay, then identifies a later departure when the original connection is missed.

The interface is in Polish. Quiet Precision combines large departure times, an interactive timeline and a pixel-art status face.

## Demo

Start both services and choose an example under **Wypróbuj przykład**. Move the delay slider to update the margin, status, timeline and Plan B.

| Example | Schedule | Try |
| --- | --- | --- |
| **Spokojna przesiadka** | Arrival 17:42, departure 17:51, walking 3 min, next departure 18:03 | Delays of 0, 6 and 8 min give margins of +6, 0 and −2 min. At 8 min, Plan B is 18:03. |
| **Przesiadka na styk** | Arrival 17:48, departure 17:52, walking 3 min, next departure 18:04 | Delays of 0, 1 and 2 min show a reachable, just-in-time and missed connection. |
| **Ostatni kurs** | Arrival 23:58, departure 00:04 the following day, walking 3 min, no later departure | A 4 min delay misses the connection and leaves no alternative. |

These are **fictional demonstration scenarios**, fixed to 10–11 November 2026 in `Europe/Warsaw`. They are not current transport timetables. Examples use the real evaluation API without being saved to SQLite. **Wróć do swoich scenariuszy** returns to the previously selected saved scenario.

### Screenshots

Real captures have not yet been added to this repository. Reserved screenshot slots:

- [ ] Desktop: transfer analysis with an 8 min delay and Plan B at 18:03.
- [ ] Mobile: the shared arrival/departure point at zero margin.
- [ ] Midnight: the last-course example with no alternative.

## Features

- Create, list, select, edit and delete scenarios, with deletion confirmation and persistent local storage.
- Enter dates through calendar controls and times as HH:MM, including an explicit choice for repeated DST hours.
- Simulate arrival delay and inspect the transfer margin and zero-delay threshold.
- Show reachable, just-in-time and missed states, with Plan B or an explicit unavailable state.
- Inspect timeline events for full dates and offsets; coincident events share one point, while nearby events remain distinct.
- Use the responsive interface with loading, empty and error states, keyboard controls and reduced-motion support.
- Explicitly import official static ZTM/SKM GTFS schedules and query them through a separate read-only backend API. The frontend schedule picker is not implemented.
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
- [Demo examples](frontend/src/demoExamples.ts) contain fixed inputs without database identifiers. Selecting one reuses the analysis component and does not call the CRUD write endpoints.
- [GTFS integration](docs/gtfs.md) uses a separate local SQLite database and explicit CLI imports. Startup and API requests never download feeds; transfer evaluation remains independent.

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
| GET | `/api/transit/transfer-links` | Describe the single explicit stop pair and unverified walking assumption. |
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

No manual database setup, accounts or API keys are required. Saved scenarios remain in SQLite after the backend restarts.

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

Frontend unit tests cover Warsaw time conversion, fixed demo inputs, timeline event grouping, close timestamps and API response validation. The build script also runs the typecheck. There is no committed browser end-to-end suite.

## Engineering Decisions

- **Time handling:** API inputs require full ISO 8601 dates with offsets valid for `Europe/Warsaw`. The form rejects nonexistent spring-transition times and asks which occurrence to use during the autumn overlap. SQLite stores ISO strings to preserve offsets.
- **Elapsed time:** the backend converts inputs to UTC before arithmetic and comparisons. Full dates handle midnight and DST without comparing clock times alone.
- **Transfer boundaries:** `margin = departure − (arrival + delay + walking)`. Positive means `Zdążysz`, zero means `Na styk`, and negative means `Nie zdążysz`. The threshold is the margin at zero delay; non-positive thresholds indicate no safe initial margin.
- **Plan B:** only a missed connection needs an alternative. The backend chooses the earliest supplied later departure at or after the expected arrival at the stop. Candidates must belong to the same departing line and direction; the application does not search a transport network.
- **Asynchronous UI:** analysis requests are debounced by 150 ms. Cleanup aborts superseded requests, and a disposal guard ignores late responses. Results are matched to the current scenario, delay and retry attempt.
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
- Connect imported GTFS schedules to scenario creation after validating interchange pairs and walking times.
