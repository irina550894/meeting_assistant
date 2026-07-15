from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.booking import UserProfile
from app.interfaces.http.dependencies import (
    get_current_mini_app_user,
    get_mini_app_analytics_service,
)
from app.main import create_app

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)

USER = UserProfile(
    id=uuid4(),
    telegram_id=1001,
    telegram_username="client",
    full_name="Client",
)


class FakeAnalyticsService:
    def __init__(self) -> None:
        self.events = []

    async def track_event(self, *, user, event_name, payload=None) -> None:
        self.events.append((user, event_name, payload))


async def current_user_override():
    return USER


def analytics_api_client() -> tuple[TestClient, FakeAnalyticsService]:
    app = create_app()
    analytics = FakeAnalyticsService()
    app.dependency_overrides[get_current_mini_app_user] = current_user_override
    app.dependency_overrides[get_mini_app_analytics_service] = lambda: analytics
    return TestClient(app), analytics


def test_mini_app_analytics_event_is_recorded_for_current_user() -> None:
    client, analytics = analytics_api_client()

    response = client.post(
        "/api/miniapp/analytics/event",
        json={"event_name": "booking_form_opened", "payload": {"screen": "booking"}},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert analytics.events == [(USER, "booking_form_opened", {"screen": "booking"})]


def test_mini_app_analytics_requires_session_cookie_without_override() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/miniapp/analytics/event",
        json={"event_name": "booking_form_opened"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "mini_app_session_missing"
