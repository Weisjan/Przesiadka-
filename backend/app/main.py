from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime
import json

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .database import validate_database_paths
from .gtfs.api import router as transit_router
from .gtfs.sources import configured_path
from .gtfs.store import read_connection
from .walking.api import router as walking_router
from .walking.store import configured_path as walking_path


def create_app(transit_database_path: Path | None = None,
               walking_database_path: Path | None = None, *, demo: dict | None = None) -> FastAPI:
    transit_database_path = (transit_database_path or configured_path()).resolve()
    walking_database_path = (walking_database_path or walking_path()).resolve()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        validate_database_paths(transit_database_path, walking_database_path)
        if demo is None and transit_database_path.is_file():
            with read_connection(transit_database_path) as connection:
                if any(json.loads(row[0]).get("demo_subset") for row in connection.execute("SELECT metadata FROM gtfs_sources")):
                    raise ValueError("Archiwalny wycinek wymaga jawnego uruchomienia przez app.demo serve; nie jest bieżącym rozkładem.")
        yield

    app = FastAPI(title="Przesiadka+", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.transit_database_path = transit_database_path
    app.state.walking_database_path = walking_database_path
    app.state.demo = demo
    app.state.walking_reference_at = datetime.fromisoformat(demo["walking_reference_at"]) if demo else None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(transit_router)
    app.include_router(walking_router)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        # Echoing invalid input (e.g. NaN) can itself fail JSON serialization.
        return JSONResponse(status_code=422, content={"detail": [
            {"loc": item["loc"], "msg": item["msg"], "type": item["type"]}
            for item in error.errors()
        ]})

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
