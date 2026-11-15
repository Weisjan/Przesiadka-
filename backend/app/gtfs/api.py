from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from ..models import WarsawDatetime
from ..walking.client import WalkingError

from .sources import GTFSError
from .store import sources
from .suggestions import SuggestionInput, suggest_transfers
from .planner import PlanInput, WINDOW_HOURS, plan_journey, planner_stops, requested_instant
from .transfer_search import LINK, SearchError, TransferSearchInput, journeys, search_transfers, transfer_links

router = APIRouter(prefix="/api/transit", tags=["transit"])


def database_path(request: Request) -> Path:
    return request.app.state.transit_database_path


Database = Annotated[Path, Depends(database_path)]


def with_demo(result: dict, request: Request) -> dict:
    if request.app.state.demo:
        result["demo"] = {key: request.app.state.demo[key] for key in ("label", "walking_reference_at", "window_start_at", "window_end_at")}
    return result


@router.get("/journeys/stops")
def get_planner_stops(database: Database, operator: Literal["skm", "ztm"],
                      query: str = Query(default="", max_length=120), limit: int = Query(default=25, ge=1, le=100)):
    try:
        return planner_stops(database, operator, query, limit)
    except GTFSError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/journeys/plan")
def post_journey_plan(data: PlanInput, database: Database, request: Request):
    try:
        demo = request.app.state.demo
        if demo:
            start = requested_instant(data).astimezone(timezone.utc)
            if start < datetime.fromisoformat(demo["window_start_at"]) or start + timedelta(hours=WINDOW_HOURS) > datetime.fromisoformat(demo["window_end_at"]):
                raise SearchError(422, "demo_out_of_range", "Archiwalne demo obsługuje wyjazdy 13.11.2026 od 16:00 do 18:00. Wybierz godzinę z tego zakresu lub gotowy przykład.")
        return with_demo(plan_journey(database, data, request.app.state.walking_database_path, request.app.state.walking_reference_at), request)
    except SearchError as error:
        raise HTTPException(status_code=error.status, detail=error.detail) from error
    except GTFSError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/transfers/suggest")
def post_transfer_suggestions(data: SuggestionInput, database: Database, request: Request):
    if request.app.state.demo:
        raise HTTPException(status_code=409, detail="W archiwalnym demo użyj wyszukiwarki podróży skąd/kiedy/dokąd.")
    try:
        return suggest_transfers(database, data, request.app.state.walking_database_path)
    except SearchError as error:
        raise HTTPException(status_code=error.status, detail=error.detail) from error
    except GTFSError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/transfer-links")
def get_transfer_links(database: Database, request: Request):
    try:
        return with_demo(transfer_links(database, request.app.state.walking_database_path, request.app.state.walking_reference_at), request)
    except SearchError as error:
        raise HTTPException(status_code=error.status, detail=error.detail) from error
    except GTFSError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/transfers/search")
def post_transfer_search(data: TransferSearchInput, database: Database, request: Request):
    try:
        return with_demo(search_transfers(database, data, request.app.state.walking_database_path, request.app.state.walking_reference_at), request)
    except SearchError as error:
        raise HTTPException(status_code=error.status, detail=error.detail) from error
    except GTFSError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except WalkingError as error:
        raise HTTPException(status_code=503, detail={"code": error.code, "message": str(error)}) from error


@router.get("/sources")
def get_sources(database: Database, request: Request):
    try:
        return {"is_realtime": False, "sources": sources(database), "demo": request.app.state.demo}
    except GTFSError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/journeys")
def get_journeys(database: Database, request: Request, leg: Literal["arrival", "departure"],
                 date: str = Query(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"),
                 limit: int = Query(default=2000, ge=1, le=2000),
                 after: WarsawDatetime | None = Query(default=None),
                 link_id: str = Query(default=LINK.id, min_length=1, max_length=80)):
    if request.app.state.demo:
        raise HTTPException(status_code=409, detail="Archiwalny wycinek obsługuje wyszukiwarkę podróży, a nie pełną listę kursów dnia.")
    try:
        day = Date.fromisoformat(date)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Podaj poprawną datę RRRR-MM-DD.") from error
    try:
        return journeys(database, leg, day, limit, after, link_id)
    except SearchError as error:
        raise HTTPException(status_code=error.status, detail=error.detail) from error
    except GTFSError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
