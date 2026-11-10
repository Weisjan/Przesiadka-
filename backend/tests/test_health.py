import pytest
from fastapi.testclient import TestClient

def test_health(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_allowed_cors_origin(origin: str, client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": origin})

    assert response.headers["access-control-allow-origin"] == origin

    preflight = client.options(
        "/api/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin


def test_other_cors_origin_is_not_allowed(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": "http://localhost:9999"})

    assert "access-control-allow-origin" not in response.headers
