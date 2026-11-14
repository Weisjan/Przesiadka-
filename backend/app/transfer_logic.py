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


def evaluate_transfer(
    arrival_at: datetime,
    departure_at: datetime,
    walking_minutes: int,
    delay_minutes: float,
) -> TransferEvaluation:
    """Compare UTC instants using a simulated delay and estimated walking time."""
    for value in (walking_minutes, delay_minutes):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
            raise ValueError("Opóźnienie i dojście muszą być nieujemnymi, skończonymi liczbami minut.")
    for value in (arrival_at, departure_at):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Daty muszą zawierać strefę lub offset czasu.")

    try:
        # UTC arithmetic measures elapsed time even when both inputs share a DST zone.
        departure = departure_at.astimezone(timezone.utc)
        initial_arrival = arrival_at.astimezone(timezone.utc) + timedelta(minutes=walking_minutes)
        expected_arrival = initial_arrival + timedelta(minutes=delay_minutes)
        threshold = departure - initial_arrival
        margin = departure - expected_arrival
        zero = timedelta(0)
        warsaw = ZoneInfo("Europe/Warsaw")
        return TransferEvaluation(
            margin_minutes=margin.total_seconds() / 60,
            delay_threshold_minutes=threshold.total_seconds() / 60,
            status="Zdążysz" if margin > zero else "Na styk" if margin == zero else "Nie zdążysz",
            has_safe_margin=threshold > zero,
            expected_stop_arrival_at=expected_arrival.astimezone(warsaw),
        )
    except OverflowError as error:
        raise ValueError("Wynik obliczeń jest poza obsługiwanym zakresem dat.") from error
