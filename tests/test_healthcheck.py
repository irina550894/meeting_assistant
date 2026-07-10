from fastapi.testclient import TestClient

from app.main import create_app


def test_healthcheck_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health", headers={"x-operation-id": "op-health"})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "meeting-assistant"
    assert response.headers["x-operation-id"] == "op-health"
