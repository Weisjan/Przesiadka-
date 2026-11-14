from datetime import date as Date
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from ..models import WarsawDatetime
from ..walking.client import WalkingError

from .sources import GTFSError
from .store import sources
from .suggestions import SuggestionInput, suggest_transfers
from .transfer_search import LINK, SearchError, TransferSearchInput, journeys, search_transfers, transfer_links

router = APIRouter(prefix="/api/transit", tags=["transit"])


def database_path(request: Request) -> Path:
    return request.app.state.transit_database_path


Database = Annotated[Path, Depends(database_path)]


@router.post("/transfers/suggest")
def post_transfer_suggestions(data: SuggestionInput, database: Database, request: Request):
    try:
        return suggest_transfers(database, data, request.app.state.walking_database_path)
    except SearchError as error:
        raise HTTPException(status_code=error.status, detail=error.detail) from error
    except GTFSError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/transfer-links")
def get_transfer_links(database: Database, request: Request):
    try:
        return transfer_links(database, request.app.state.walking_database_path)
    except SearchError as error:
        raise HTTPException(status_code=error.status, detail=error.detail) from error
    except GTFSError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/transfers/search")
def post_transfer_search(data: TransferSearchInput, database: Database, request: Request):
    try:
        return search_transfers(database, data, request.app.state.walking_database_path)
    except SearchError as error:
        raise HTTPException(status_code=error.status, detail=error.detail) from error
    except GTFSError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except WalkingError as error:
        raise HTTPException(status_code=503, detail={"code": error.code, "message": str(error)}) from error


@router.get("/sources")
def get_sources(database: Database):
    try:
        return {"is_realtime": False, "sources": sources(database)}
    except GTFSError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/journeys")
def get_journeys(database: Database, leg: Literal["arrival", "departure"],
                 date: str = Query(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"),
                 limit: int = Query(default=2000, ge=1, le=2000),
                 after: WarsawDatetime | None = Query(default=None),
                 link_id: str = Query(default=LINK.id, min_length=1, max_length=80)):
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
