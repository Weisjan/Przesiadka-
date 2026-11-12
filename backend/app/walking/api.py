from fastapi import APIRouter, HTTPException, Query, Request

from ..gtfs.sources import GTFSError
from .client import WalkingError
from .store import lookup
from .nearby import nearby

router = APIRouter(prefix="/api/transit", tags=["walking"])


@router.get("/nearby-stops")
def get_nearby_stops(request: Request, stop_id: str = Query(pattern=r"^(skm|ztm):.+$", max_length=260),
                     radius_m: float = Query(default=500, gt=0, le=2000, allow_inf_nan=False),
                     limit: int = Query(default=50, ge=1, le=100)):
    try:
        return nearby(request.app.state.transit_database_path, request.app.state.walking_database_path, stop_id, radius_m, limit)
    except WalkingError as error:
        status = 404 if error.code == "stop_not_found" else 422 if error.code in ("invalid_parameters", "invalid_stop", "invalid_coordinates") else 503
        raise HTTPException(status_code=status, detail={"code": error.code, "message": str(error)}) from error
    except GTFSError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/walking-transfers")
def get_walking_transfer(request: Request,
                         from_stop_id: str = Query(pattern=r"^(skm|ztm):.+$", max_length=260),
                         to_stop_id: str = Query(pattern=r"^(skm|ztm):.+$", max_length=260)):
    try:
        return lookup(request.app.state.walking_database_path, request.app.state.transit_database_path, from_stop_id, to_stop_id)
    except WalkingError as error:
        status = 404 if error.code == "stop_not_found" else 422 if error.code in ("invalid_pair", "invalid_stop", "invalid_coordinates") else 503
        raise HTTPException(status_code=status, detail={"code": error.code, "message": str(error)}) from error
    except GTFSError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
