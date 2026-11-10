from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .models import WarsawDatetime
from .transfer_logic import TransferEvaluation, evaluate_transfer

router = APIRouter(prefix="/api/transfers", tags=["transfers"])


class TransferInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arrival_at: WarsawDatetime
    departure_at: WarsawDatetime
    walking_minutes: Annotated[int, Field(strict=True, ge=0, le=1440)]
    delay_minutes: Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
    next_departures: list[WarsawDatetime] = Field(
        max_length=100,
        description="Kolejne odjazdy tej samej linii i w tym samym kierunku; kolejność dowolna.",
    )


@router.post("/evaluate", response_model=TransferEvaluation)
def evaluate(data: TransferInput) -> TransferEvaluation:
    """Ocena podanych czasów bez odczytu ani zapisu scenariusza w bazie.

    has_safe_margin=false oznacza brak bezpiecznego marginesu już bez opóźnienia.
    plan_b_status: not_needed — kurs osiągalny, available — alternatywa znaleziona,
    unavailable — brak osiągalnego kolejnego kursu. Wszystkie czasy trwania w minutach.
    """
    try:
        return evaluate_transfer(**data.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
