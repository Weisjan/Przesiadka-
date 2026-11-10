from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Literal
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class TransferEvaluation:
    margin_minutes: float
    delay_threshold_minutes: float
    status: Literal["Zdążysz", "Na styk", "Nie zdążysz"]
    has_safe_margin: bool
    expected_stop_arrival_at: datetime
    plan_b_status: Literal["not_needed", "available", "unavailable"]
    plan_b_departure_at: datetime | None


def evaluate_transfer(
    arrival_at: datetime,
    departure_at: datetime,
    walking_minutes: int,
    delay_minutes: float,
    next_departures: list[datetime],
) -> TransferEvaluation:
    """Evaluate elapsed time; candidates belong to the same departure line/direction.

    Datetimes must be aware. The API additionally validates Warsaw local offsets.
    The candidate list is never modified and need not be sorted.
    """
    for value in (walking_minutes, delay_minutes):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
            raise ValueError("Opóźnienie i dojście muszą być nieujemnymi, skończonymi liczbami minut.")
    for value in (arrival_at, departure_at, *next_departures):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Daty muszą zawierać strefę lub offset czasu.")

    try:
        # UTC arithmetic measures elapsed time even when both inputs share a DST zone.
        departure = departure_at.astimezone(timezone.utc)
        initial_arrival = arrival_at.astimezone(timezone.utc) + timedelta(minutes=walking_minutes)
        expected_arrival = initial_arrival + timedelta(minutes=delay_minutes)
        candidates = [value.astimezone(timezone.utc) for value in next_departures]
        if any(value <= departure for value in candidates):
            raise ValueError("Kolejne odjazdy muszą być późniejsze od pierwotnego kursu.")
        threshold = departure - initial_arrival
        margin = departure - expected_arrival
        zero = timedelta(0)
        plan_b = min((value for value in candidates if value >= expected_arrival), default=None) if margin < zero else None
        warsaw = ZoneInfo("Europe/Warsaw")
        return TransferEvaluation(
            margin_minutes=margin.total_seconds() / 60,
            delay_threshold_minutes=threshold.total_seconds() / 60,
            status="Zdążysz" if margin > zero else "Na styk" if margin == zero else "Nie zdążysz",
            has_safe_margin=threshold > zero,
            expected_stop_arrival_at=expected_arrival.astimezone(warsaw),
            plan_b_status="not_needed" if margin >= zero else "available" if plan_b else "unavailable",
            plan_b_departure_at=plan_b.astimezone(warsaw) if plan_b else None,
        )
    except OverflowError as error:
        raise ValueError("Wynik obliczeń jest poza obsługiwanym zakresem dat.") from error
