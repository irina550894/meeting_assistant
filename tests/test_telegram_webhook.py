from fastapi.testclient import TestClient

from app.main import create_app


def test_telegram_webhook_disabled_in_local_mode() -> None:
    client = TestClient(create_app())

    response = client.post("/telegram/webhook", json={"update_id": 1})

    assert response.status_code == 404
