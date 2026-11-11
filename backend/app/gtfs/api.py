from datetime import date as Date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .sources import GTFSError
from .store import departures, search_stops, sources

router = APIRouter(prefix="/api/transit", tags=["transit"])


def database_path(request: Request) -> Path:
    return request.app.state.transit_database_path


Database = Annotated[Path, Depends(database_path)]


@router.get("/sources")
def get_sources(database: Database):
    try:
        return {"is_realtime": False, "sources": sources(database)}
    except GTFSError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/stops")
def get_stops(database: Database, query: str = Query(default="", max_length=120), limit: int = Query(default=50, ge=1, le=100)):
    try:
        return {"is_realtime": False, "stops": search_stops(database, query, limit), "limit": limit}
    except GTFSError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/departures")
def get_departures(database: Database, stop_id: str = Query(pattern=r"^(ztm|skm):.+$", max_length=260),
                   date: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"), limit: int = Query(default=50, ge=1, le=200)):
    try:
        day = Date.fromisoformat(date)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Podaj poprawną datę RRRR-MM-DD.") from error
    try:
        result = departures(database, stop_id, day, limit)
    except GTFSError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if result is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono przystanku w lokalnym imporcie GTFS.")
    return result
