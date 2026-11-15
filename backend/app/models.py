import re
from datetime import datetime, timezone
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import AfterValidator, AwareDatetime, BeforeValidator

WARSAW = ZoneInfo("Europe/Warsaw")


def require_iso_datetime(value: object) -> object:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?[+-]\d{2}:\d{2}", value
    ):
        raise ValueError("Podaj pełną datę ISO 8601 z offsetem czasu Warszawy.")
    return value


def validate_warsaw_offset(value: datetime) -> datetime:
    try:
        local = value.astimezone(WARSAW)
    except (OverflowError, ValueError) as error:
        raise ValueError("Data jest poza obsługiwanym zakresem.") from error
    if local.utcoffset() != value.utcoffset() or local.replace(tzinfo=None) != value.replace(tzinfo=None):
        raise ValueError("Data nie istnieje w Warszawie lub ma nieprawidłowy offset czasu.")
    return value


WarsawDatetime = Annotated[
    AwareDatetime, BeforeValidator(require_iso_datetime), AfterValidator(validate_warsaw_offset)
]
