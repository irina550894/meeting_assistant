from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.application import MiniAppAuthError, MiniAppAuthResult
from app.core.booking import BookingService
from app.interfaces.http.dependencies import get_mini_app_auth_service
from app.main import create_app

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


class SuccessfulAuthService:
    async def authenticate(self, raw_init_data: str) -> MiniAppAuthResult:
        service = BookingService()
        user = service.create_or_update_user(
            telegram_id=1001,
            telegram_username="irina",
            now=NOW,
        )
        user.full_name = "Irina Admin"
        return MiniAppAuthResult(
            user=user,
            session_token="session-token",
            expires_at=NOW + timedelta(hours=12),
            is_admin=True,
        )


class FailingAuthService:
    async def authenticate(self, raw_init_data: str) -> MiniAppAuthResult:
        raise MiniAppAuthError("invalid_hash", "Telegram initData hash is invalid.")


def test_miniapp_auth_route_sets_session_cookie() -> None:
    app = create_app()
    app.dependency_overrides[get_mini_app_auth_service] = lambda: SuccessfulAuthService()
    client = TestClient(app)

    response = client.post(
        "/api/miniapp/auth/telegram",
        json={"init_data": "signed-init-data"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["telegram_id"] == 1001
    assert body["user"]["telegram_username"] == "irina"
    assert body["user"]["full_name"] == "Irina Admin"
    assert body["user"]["is_admin"] is True
    set_cookie = response.headers["set-cookie"]
    assert "meeting_assistant_mini_app_session=session-token" in set_cookie
    assert "HttpOnly" in set_cookie


def test_miniapp_auth_route_returns_401_for_invalid_init_data() -> None:
    app = create_app()
    app.dependency_overrides[get_mini_app_auth_service] = lambda: FailingAuthService()
    client = TestClient(app)

    response = client.post(
        "/api/miniapp/auth/telegram",
        json={"init_data": "bad-init-data"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_hash"
    assert "bad-init-data" not in str(response.json())
