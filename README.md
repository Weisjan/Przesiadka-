# Przesiadka+

A local, single-screen MVP for planning one SKM ride, an estimated walk and one ZTM ride in Gdańsk. Enter an SKM origin, a departure date/time and a ZTM destination. The backend compares trains and downstream approved interchanges, including arrival at the destination. Simulate 0–30 minutes of delay without changing the selected courses.

Kinetic Transit presents two journey cards, an animated SVG figure and the delay slider. The interface is in Polish. Timetables are imported static GTFS data. Walking time comes exclusively from a current directional OpenRouteService cache entry and remains estimated. Results are the best found within the supported links and search window, not globally fastest routes.

## Run locally

For the recruitment presentation, use the separate historical demo below. Regular startup uses the normal local feeds and current walking-cache freshness.

Python 3.13, uv, Node.js 24 and npm are required. Run these blocks in separate PowerShell terminals from the repository root.

```powershell
Set-Location .\backend
uv sync --locked
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
Set-Location .\frontend
npm.cmd ci
npm.cmd run dev
```

Open <http://127.0.0.1:5173>. Stop each process with Ctrl+C. When updating an existing environment, stop its old backend first so Windows can release loaded dependency files.

## Local data and API

[GTFS imports](docs/gtfs.md) and [walking imports](docs/walking.md) are explicit CLI operations. Startup and HTTP requests read local data. Configure paths through `PRZESIADKA_TRANSIT_PATH` and `PRZESIADKA_WALKING_PATH`. Both SQLite stores validate their application IDs/schema; the application rejects path aliases. Existing unrelated local databases are retained.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Diagnostics |
| GET | `/api/transit/sources` | Feed coverage and attribution |
| GET | `/api/transit/transfer-links` | Approved directional pairs and cache state |
| GET | `/api/transit/journeys` | Exact course occurrences for a pair and Warsaw civil date |
| GET | `/api/transit/journeys/stops` | Search SKM origin stations or grouped ZTM destination poles |
| POST | `/api/transit/journeys/plan` | Compare one-transfer journeys from an origin to a destination |
| GET | `/api/transit/walking-transfers` | Saved directional walking estimate |
| POST | `/api/transit/transfers/suggest` | Rank scheduled courses across approved links for a selected SKM arrival and goal |
| POST | `/api/transit/transfers/search` | Evaluate the selected course using current cached walking time |

[Journey planner contract and limits](docs/journey-planner.md), [approved pairs and legacy selected-course API](docs/transfer-links.md). OpenAPI JSON is available at `/openapi.json`.

## Demo rekrutacyjne

Three verified journeys use a separate historical snapshot for **13 November 2026**. In demo mode, **Zobacz przykład** fills the planner and runs the real backend. The original ORS measurements are replayed at their recorded historical reference time; regular mode still rejects expired cache.

Prepare once from the existing official local imports and saved ORS cache, then retain the ignored `backend/data/demo/` directory:

```powershell
uv run --no-sync --directory backend python -m app.demo prepare
uv run --no-sync --directory backend python -m app.demo serve
```

Run `npm.cmd run dev --prefix frontend` in another terminal and open <http://127.0.0.1:5173>. Stop the regular backend before serving demo on port 8000. Dependencies must already be installed. Preparation refuses an existing output directory and makes no network requests. The current snapshot is already prepared locally; it is not part of Git.

[Presentation guide, expected results, data provenance and redistribution limits](docs/demo.md). Keep the snapshot with its matching code version; current public feeds may no longer contain this historical date. This mode is an archival demonstration, not today's timetable.

## Tests

```powershell
uv run --directory backend python -m pytest
npm.cmd test --prefix frontend
npm.cmd run build --prefix frontend
```

Backend tests use temporary databases and synthetic feed/provider fixtures. The frontend build includes TypeScript checking. Browser smoke checks use isolated copies of local feeds and walking data.

## Calculation and limits

The pure Python evaluator compares UTC instants, preserving full Warsaw dates and offsets across midnight/DST. Margin equals departure minus arrival, simulated delay and walking time. Positive is `Zdążysz`, zero `Na styk`, negative `Nie zdążysz`. Fractional cached walking seconds are rounded up to whole minutes.

Journey ranking first prefers at least two minutes of transfer margin, then earlier destination arrival, shorter onboard-to-destination duration, shorter waiting after walking and stable IDs. Destination groups are checked against actual downstream stop occurrences. **Inne podróże** offers up to two alternatives. The slider preserves the selected SKM/ZTM courses; changing an alternative or destination preserves the simulated delay. Editing search fields clears the previous result until a new plan is selected.

The current approved registry covers four directional links at Gdańsk Główny. Trains from other stations are considered only if their downstream stops reach a supported interchange. No other hub or line is preferred or automatically approved. The planner uses a six-hour horizon for boarding and destination arrival, checks both feeds' coverage and refuses incomplete searches when hard limits are exceeded. It never requests live ORS routes. Local feed bounds are 2026-10-19–2026-12-12 for SKM and 2026-11-11–2026-11-25 for ZTM in the inspected snapshots; the API checks the actual imported metadata.

The UI requests the exact trip, service date, route and stop sequence. Aborted requests and input keys prevent stale results from replacing current selections. Missing, expired or coordinate-mismatched walking data excludes a link from suggestions and blocks its evaluation. GTFS coverage and calendars are checked on the backend. The SKM feed does not identify physical platforms. Walking accessibility and actual delays require independent verification.

The supplied SVG models use native SMIL with 1.2 s walking, 0.6 s running and 2.4 s standing cycles. The figure is green for a margin of at least two minutes, red from zero to under two minutes, and grey below zero. These presentation bands use the exact backend margin. A 250 ms opacity transition preserves the models and their animation timelines. Reduced motion pauses SMIL at its initial frame.

The Edge regression suite uses synthetic API fixtures and requires an existing Python Playwright installation. Start Vite in one terminal, then run `python frontend/tests/stop_selection_browser.py` from the repository root in that environment. It writes screenshots and motion evidence to a temporary directory. `PRZESIADKA_UI_URL` and `PRZESIADKA_ARTIFACTS` override its UI address and artifact directory.
