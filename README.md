# Przesiadka+

A local full-stack application for planning an SKM train ride and a ZTM connection in Gdańsk. It selects an interchange, includes estimated walking time and shows how a simulated train delay changes the transfer margin.

## Demo

[Watch the demo with Polish narration and captions (MP4, 2:45)](demo-video/final/przesiadka-demo-ai-voice.mp4)

The film records the working Kinetic Transit interface using archival timetables from 13 November 2026. [Production scripts and storyboard](demo-video/README.md) are included.

## Features

- Choose an SKM origin, departure date/time and ZTM destination.
- Find connections through approved walking links and exact ZTM boarding stops.
- Compare up to three journeys, including destination arrival times.
- Inspect estimated walking time and the remaining transfer margin.
- Simulate 0 to 30 minutes of delay for the selected courses.
- Follow the result through animated SVG figures and a responsive, keyboard-accessible Polish interface.

## Tech Stack

| Area | Technologies |
|---|---|
| Frontend | React, TypeScript, Vite, CSS Modules, SVG/SMIL |
| Backend | Python 3.13, FastAPI, Pydantic, uvicorn; dependencies managed with uv |
| Database | SQLite through Python's `sqlite3` |
| Transit data | Locally imported SKM and ZTM Gdańsk GTFS |
| Walking estimates | Saved directional OpenRouteService routes |
| Testing | pytest/httpx, Node test runner, Playwright with Edge |

## How It Works

The backend follows later stops of each candidate SKM trip and checks approved walking links to concrete ZTM stops. A connecting bus or tram must reach the destination later on that same trip. Walking estimates come from the local ORS cache and are rounded up to whole minutes.

Within a six-hour search window, ranking prefers at least two minutes of transfer margin, then earlier destination arrival, shorter journey duration and less waiting. The current registry contains four directional links at Gdańsk Główny.

A pure Python function calculates `margin = departure - (arrival + walking + delay)`, comparing UTC instants across midnight and Warsaw DST changes. The slider evaluates the same courses with a simulated delay. Request cancellation and response identity checks protect the UI against stale results. [Planner details](docs/journey-planner.md).

## Getting Started

### Prerequisites and installation

Use Windows PowerShell with Git, Python 3.13, uv, Node.js 24+ and npm installed.

```powershell
git clone --branch feature/gtfs-integration https://github.com/Weisjan/Przesiadka-.git PrzesiadkaPlus
Set-Location .\PrzesiadkaPlus
uv sync --locked --directory backend
npm.cmd ci --prefix frontend
```

Run all following commands from this repository root. The frontend's `package.json` is in `frontend/`.

### Prepare local data

Import both official static timetables:

```powershell
uv run --no-sync --directory backend python -m app.gtfs ztm
uv run --no-sync --directory backend python -m app.gtfs skm
```

These commands download and import the feeds into `backend/data/gtfs/transit.db`. With an ORS key supplied through the process environment variable `ORS_API_KEY`, preview and calculate one supported walking link:

```powershell
uv run --no-sync --directory backend python -m app.walking skm:7500 ztm:2001 --dry-run
uv run --no-sync --directory backend python -m app.walking skm:7500 ztm:2001 --max-requests 1
```

The second command contacts ORS and saves the estimate in `backend/data/walking.db`. Search uses the approved links with valid cached estimates. [GTFS imports](docs/gtfs.md) and [walking-cache setup](docs/walking.md) document paths, attribution and controlled imports for further pairs. Keep keys and provider databases local.

### Start the application

Start the API:

```powershell
uv run --no-sync --directory backend uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second PowerShell terminal at the repository root, start the frontend:

```powershell
npm.cmd run dev --prefix frontend
```

Open <http://127.0.0.1:5173>. API health is at <http://127.0.0.1:8000/api/health> and its schema at <http://127.0.0.1:8000/openapi.json>. Stop servers with Ctrl+C.

### Historical presentation mode

The recorded examples use `backend/data/demo/transit.db`, `walking.db` and `manifest.json`. This local bundle is excluded from Git. Rebuilding it with `app.demo prepare` requires existing official imports covering 13 November 2026 and the saved walking estimates; current feeds may cover different dates. [Demo preparation and provenance](docs/demo.md).

With the bundle present, use this command instead of the regular API command:

```powershell
uv run --no-sync --directory backend python -m app.demo serve
```

Use the same frontend command. The archival banner identifies this mode. **Zobacz przykład** runs the planner for Wrzeszcz to Strzyża PKM, Lawendowe Wzgórze or Przegalina. Departure searches cover 13 November 2026, 16:00 to 18:00; delays remain simulated.

## Testing

From the repository root:

```powershell
uv run --no-sync --directory backend python -m pytest -q
npm.cmd test --prefix frontend
npm.cmd run typecheck --prefix frontend
npm.cmd run build --prefix frontend
```

Tests use temporary databases and synthetic provider fixtures. The [browser suite](frontend/tests/stop_selection_browser.py) checks interaction, stale responses, responsive layout and SVG motion using an existing Playwright/Edge installation.

## AI-Assisted Development

OpenAI Codex supported implementation, tests, refactoring and browser/video automation. I defined the product flow, technical constraints and visual direction, reviewed changes and used tests to verify behaviour. The [agent instructions](AGENTS.md) and [project skills](.agents/skills) are versioned. Humanizer 4.0.0 helped edit README prose, film narration and captions; Playwright and FFmpeg automated the recording and montage.
