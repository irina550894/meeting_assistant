from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application import MiniAppAnalyticsDeps, MiniAppAnalyticsService
from app.core.booking import UserProfile

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


class FailingStore:
    async def record_event(self, *, user, event_name, payload, created_at) -> None:
        raise RuntimeError("database is unavailable")


class RecordingStore:
    def __init__(self) -> None:
        self.events = []

    async def record_event(self, *, user, event_name, payload, created_at) -> None:
        self.events.append((user, event_name, payload, created_at))


def user() -> UserProfile:
    return UserProfile(id=uuid4(), telegram_id=1001)


def clock() -> datetime:
    return NOW


@pytest.mark.asyncio
async def test_mini_app_analytics_records_event() -> None:
    store = RecordingStore()
    profile = user()
    service = MiniAppAnalyticsService(MiniAppAnalyticsDeps(store=store, clock=clock))

    await service.track_event(
        user=profile,
        event_name="booking_form_opened",
        payload={"screen": "booking"},
    )

    assert store.events == [
        (profile, "booking_form_opened", {"screen": "booking"}, NOW)
    ]


@pytest.mark.asyncio
async def test_mini_app_analytics_does_not_raise_on_store_error() -> None:
    service = MiniAppAnalyticsService(MiniAppAnalyticsDeps(store=FailingStore(), clock=clock))

    await service.track_event(user=user(), event_name="booking_form_opened")
