# Przesiadka+

A local full-stack MVP for planning an SKM train ride, an estimated walk and a ZTM connection in Gda?sk. Enter an origin, departure time and destination, then simulate how a train delay changes the transfer margin.

## Demo

[Watch or download the captioned demo (MP4, 2:45)](demo-video/final/przesiadka-demo-subtitled.mp4)

The film shows the real Kinetic Transit interface and local API, followed by diagrams explaining the implementation. It has Polish captions and no audio. Its timetable is archival, not live. [Production scripts and storyboard](demo-video/README.md) are included; clean masters, source recordings and TTS audio remain local.

## Features

- Search SKM origin stations and ZTM destinations from imported GTFS records.
- Automatically select an approved interchange and an exact ZTM boarding pole.
- Compare up to three journeys using transfer margin and destination arrival.
- Simulate 0?30 minutes of delay while keeping the selected courses fixed.
- Display the result with animated SVG figures, keyboard controls and reduced-motion support.
- Run three historical examples through the actual planner in a separate demo mode.

## Tech Stack

| Layer | Technologies |
|---|---|
| Frontend | React, TypeScript, Vite, CSS Modules, SVG/SMIL |
| Backend | Python 3.13, FastAPI, Pydantic, uvicorn, uv |
| Data | SQLite through Python `sqlite3`, static GTFS, OpenRouteService walking cache |
| Tests | pytest/httpx, Node test runner, Playwright with Edge |
| Video tools | Python, Playwright, FFmpeg/ffprobe |

## How It Works

`POST /api/transit/journeys/plan` searches candidate SKM departures and later stops of each exact train trip. It checks approved directional walks, then ZTM trips that reach the requested destination after the boarding stop. Walking estimates must be fresh and match the GTFS coordinates; fractional seconds are rounded up to minutes.

Ranking prefers at least two minutes of transfer margin, then earlier destination arrival, shorter journey duration and less waiting. The search covers a six-hour window. It does not infer walking links from matching names or select a preferred hub independently of the data.

The slider calls `POST /api/transit/transfers/search` for the same courses. A pure Python function calculates margin as scheduled departure minus arrival, simulated delay and walking time. It compares UTC instants while preserving Warsaw dates and offsets across midnight and DST. Cancellation and input identity checks protect the UI against stale responses.

[Planner contract](docs/journey-planner.md) ? [Approved links and retained APIs](docs/transfer-links.md)

## Getting Started

All commands below run in **Windows PowerShell from the repository root**. `package.json` is in `frontend/`.

1. **Requirements:** Python 3.13, uv, Node.js 24+ and npm. Local checks used Node.js 26.13.0. Playwright and FFmpeg are optional tools for browser tests and video production, not application dependencies.
2. **Install the locked application dependencies:**

   ```powershell
   uv sync --locked --directory backend
   npm.cmd ci --prefix frontend
   ```

3. **Prepare local data:** regular mode requires SKM/ZTM imports in `backend/data/gtfs/transit.db` and saved walking estimates in `backend/data/walking.db`. Follow [GTFS import](docs/gtfs.md) and [walking setup](docs/walking.md). These are explicit CLI operations; ORS imports require a process-local API key. No key belongs in Git or the browser. For an existing historical bundle, use Demo Mode below instead.
4. **Start the regular backend:**

   ```powershell
   uv run --no-sync --directory backend uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

5. **Start the frontend in a second terminal, also from the repository root:**

   ```powershell
   npm.cmd run dev --prefix frontend
   ```

6. **Open** <http://127.0.0.1:5173>. The API is at <http://127.0.0.1:8000>; `/api/health` checks server health and `/openapi.json` describes the endpoints. Swagger/ReDoc pages are disabled. Stop each server with Ctrl+C before switching modes.

Alternate database paths use `PRZESIADKA_TRANSIT_PATH` and `PRZESIADKA_WALKING_PATH`. Startup and searches never download feeds or call ORS. A running server alone does not imply that usable timetable and walking data are installed.

## Demo Mode

The historical bundle covers **13 November 2026**, with departure searches from 16:00 to 18:00. **Zobacz przyk?ad** fills the form and runs the real backend:

| Journey from Wrzeszcz at 17:00 | ZTM departure | Destination arrival | Initial margin |
|---|---|---|---|
| Strzy?a PKM | Tram 6, 17:15 | 17:36 | +3 min |
| Lawendowe Wzg?rze | Tram 11, 17:13 | 17:37 | +2 min |
| Przegalina | Bus 112, 17:16 | 18:21 | +5 min |

Demo mode requires these local files, excluded from Git:

```text
backend/data/demo/transit.db
backend/data/demo/walking.db
backend/data/demo/manifest.json
```

With this bundle and application dependencies installed, replace the regular backend command with:

```powershell
uv run --no-sync --directory backend python -m app.demo serve
```

Use the same frontend command and URL. Confirm the archival-demo banner. Demo mode evaluates cache freshness at its recorded reference time; regular mode still rejects expired estimates. Examples supply search inputs, not fabricated API responses.

**A fresh clone cannot reproduce this historical demo by itself.** `app.demo prepare` can build a separate bundle only from existing official local imports covering that date and the required saved walking estimates:

```powershell
uv run --no-sync --directory backend python -m app.demo prepare
```

Run preparation once, only when those inputs exist and the output directory is absent. It makes no network requests and refuses to overwrite a bundle. Current public feeds may no longer contain these historical records. No public historical data bundle or guaranteed historical-download procedure is provided. [Preparation, provenance and redistribution conditions](docs/demo.md) explain the remaining data requirements.

## Testing

From the repository root:

```powershell
uv run --no-sync --directory backend python -m pytest -q
npm.cmd test --prefix frontend
npm.cmd run typecheck --prefix frontend
npm.cmd run build --prefix frontend
```

Backend tests use temporary SQLite databases and synthetic provider/feed fixtures without live ORS calls. Frontend tests use Node's test runner; build includes TypeScript checking. There is no separate lint command.

For browser tests, start Vite first, then use an existing Python environment with Playwright and Edge:

```powershell
$BrowserPython = Read-Host 'Path to python.exe with Playwright installed'
& $BrowserPython -B .\frontend\tests\stop_selection_browser.py
```

These tests use synthetic API responses, without user database access. They check selection, alternatives, stale responses, keyboard interaction, mobile/desktop geometry and SVG motion. Real-data demo verification is a separate check.

## AI-Assisted Development

I used OpenAI Codex to help implement the backend and frontend, write tests and documentation, and automate browser checks and video production. I defined the scope, data constraints and visual direction, reviewed the proposed changes, and made decisions about the MVP and its limitations. Automated tests and browser checks supported verification; generated changes were not treated as proof of correctness.

The actual [AGENTS.md](AGENTS.md) and [local skill instructions](.agents/skills) are versioned. They include guidance for small changes, frontend design, planning, concise reporting, code review and demo verification. [Humanizer 4.0.0](.agents/skills/humanizer/SKILL.md) was used to edit README prose, the film narration and captions without changing technical facts; its instructions and MIT license are included. Playwright controlled the real browser, and FFmpeg assembled the recordings and captions. These are development tools; the application does not use an AI model to plan journeys.

## Limitations

- Four directional walks at Gda?sk G??wny are approved. One SKM ride and one ZTM ride are supported; this is not a complete transport planner or a guarantee of the fastest city route.
- Demo data are archival. Timetables are static and delays are simulated, with no live vehicle positions or actual delay feed.
- Walking is estimated, not verified platform-to-pole travel time. The SKM feed does not identify physical platforms or guarantee accessibility.
- GTFS coverage and cache freshness can prevent a search. Refreshing local data is explicit, not automatic.
- The current API has no CRUD resource workflow, and the UI has no scenario management. This MVP does **not** meet the recruitment exercise's CRUD expectation. Alternatives are chosen manually; the slider does not automatically replace a missed connection.
