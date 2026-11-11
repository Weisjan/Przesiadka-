import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .sources import GTFSError

WARSAW = ZoneInfo("Europe/Warsaw")
MAX_TIME_SECONDS = 7 * 24 * 3600 - 1
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def gtfs_date(value: str) -> str:
    if not re.fullmatch(r"\d{8}", value):
        raise GTFSError("Data GTFS musi mieć format RRRRMMDD.")
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:])).isoformat()
    except ValueError as error:
        raise GTFSError(f"Nieprawidłowa data GTFS: {value}.") from error


def gtfs_seconds(value: str) -> int | None:
    if value == "":
        return None
    if not re.fullmatch(r"\d{1,3}:[0-5]\d:[0-5]\d", value):
        raise GTFSError(f"Nieprawidłowa godzina GTFS: {value}.")
    hour, minute, second = map(int, value.split(":"))
    result = hour * 3600 + minute * 60 + second
    if result > MAX_TIME_SECONDS:
        raise GTFSError("Godzina GTFS przekracza obsługiwany zakres 0–167:59:59.")
    return result


def service_anchor(day: date) -> datetime:
    # GTFS Time is elapsed time from service-day local noon minus 12 hours.
    return datetime.combine(day, time(12), WARSAW).astimezone(timezone.utc) - timedelta(hours=12)


def service_datetime(day: date, seconds: int) -> datetime:
    return (service_anchor(day) + timedelta(seconds=seconds)).astimezone(WARSAW)
