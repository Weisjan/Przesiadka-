import re
from datetime import datetime, timezone
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import AfterValidator, AwareDatetime, BeforeValidator, ConfigDict, Field as PydanticField, model_validator
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

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


class ScenarioFields(SQLModel):
    name: str = Field(min_length=1, max_length=120)
    interchange: str = Field(min_length=1, max_length=120)
    arrival_line: str = Field(min_length=1, max_length=80)
    departure_line: str = Field(min_length=1, max_length=80)
    direction: str = Field(min_length=1, max_length=120)
    walking_minutes: Annotated[int, PydanticField(strict=True)] = Field(ge=0, le=1440)


class ScenarioInput(ScenarioFields):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    arrival_at: WarsawDatetime
    departure_at: WarsawDatetime
    next_departures: list[WarsawDatetime] = PydanticField(max_length=100)

    @model_validator(mode="after")
    def validate_next_departures(self) -> "ScenarioInput":
        previous = self.departure_at.astimezone(timezone.utc)
        for departure in self.next_departures:
            current = departure.astimezone(timezone.utc)
            if current <= previous:
                raise ValueError("Kolejne odjazdy muszą być późniejsze od odjazdu i rosnąć bez powtórzeń.")
            previous = current
        return self


class ScenarioRead(ScenarioInput):
    id: int


class Scenario(ScenarioFields, table=True):
    id: int | None = Field(default=None, primary_key=True)
    # SQLite DateTime drops offsets; ISO strings preserve the submitted instant.
    arrival_at: str
    departure_at: str
    next_departures: list[str] = Field(sa_column=Column(JSON, nullable=False))
