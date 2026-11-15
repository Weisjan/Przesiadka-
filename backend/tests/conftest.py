import pytest
from fastapi.testclient import TestClient
from app.main import create_app

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "transit.db", tmp_path / "walking.db")) as api:
        yield api
