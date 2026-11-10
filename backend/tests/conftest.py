from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(tmp_path / "test.db")) as test_client:
        yield test_client


@pytest.fixture
def scenario_data():
    return {
        "name": "Poranny dojazd",
        "interchange": "Gdańsk Główny",
        "arrival_line": "SKM",
        "departure_line": "8",
        "direction": "Jelitkowo",
        "arrival_at": "2026-11-10T08:00:00+01:00",
        "departure_at": "2026-11-10T08:07:00+01:00",
        "walking_minutes": 4,
        "next_departures": ["2026-11-10T08:17:00+01:00", "2026-11-10T08:27:00+01:00"],
    }
