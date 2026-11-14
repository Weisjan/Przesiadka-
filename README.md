# Przesiadka+

A local, single-screen MVP for checking a scheduled SKM → ZTM transfer in Gdańsk. Choose an SKM train and enter a ZTM line, direction or destination stop. The backend suggests a course, boarding stop and estimated walk across approved links. Simulate 0–30 minutes of delay for the selected course.

Dark Transit presents two journey cards, an animated SVG figure and the delay slider. The interface is in Polish. Timetables are imported static GTFS data. Walking time comes exclusively from a current directional OpenRouteService cache entry and remains estimated.

## Run locally

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
| GET | `/api/transit/walking-transfers` | Saved directional walking estimate |
| POST | `/api/transit/transfers/suggest` | Rank scheduled courses across approved links for a selected SKM arrival and goal |
| POST | `/api/transit/transfers/search` | Evaluate the selected course using current cached walking time |

[Approved pairs and request contract](docs/transfer-links.md). OpenAPI JSON is available at `/openapi.json`.

## Tests

```powershell
uv run --directory backend python -m pytest
npm.cmd test --prefix frontend
npm.cmd run build --prefix frontend
```

Backend tests use temporary databases and synthetic feed/provider fixtures. The frontend build includes TypeScript checking. Browser smoke checks use isolated copies of local feeds and walking data.

## Calculation and limits

The pure Python evaluator compares UTC instants, preserving full Warsaw dates and offsets across midnight/DST. Margin equals departure minus arrival, simulated delay and walking time. Positive is `Zdążysz`, zero `Na styk`, negative `Nie zdążysz`. Fractional cached walking seconds are rounded up to whole minutes.

Suggestions prefer reachable courses with at least two minutes of margin, followed by the shortest waiting time after walking. Destination searches check usable downstream stops on the exact trip. An empty goal shows available directions. Selection stays fixed while the delay slider updates its evaluation. Other matching courses are available through **Inny kurs**.

The UI requests the exact trip, service date, route and stop sequence. Aborted requests and input keys prevent stale results from replacing current selections. Missing, expired or coordinate-mismatched walking data excludes a link from suggestions and blocks its evaluation. GTFS coverage and calendars are checked on the backend. The SKM feed does not identify physical platforms. Walking accessibility and actual delays require independent verification.

The supplied SVG models use native SMIL with 1.2 s walking, 0.6 s running and 2.4 s standing cycles. The figure is green for a margin of at least two minutes, red from zero to under two minutes, and grey below zero. These presentation bands use the exact backend margin. A 250 ms opacity transition preserves the models and their animation timelines. Reduced motion pauses SMIL at its initial frame.

The Edge regression suite uses synthetic API fixtures and requires an existing Python Playwright installation. Start Vite in one terminal, then run `python frontend/tests/stop_selection_browser.py` from the repository root in that environment. It writes screenshots and motion evidence to a temporary directory. `PRZESIADKA_UI_URL` and `PRZESIADKA_ARTIFACTS` override its UI address and artifact directory.
