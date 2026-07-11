from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import SecretStr

from app.core.booking import (
    BookingRecord,
    BookingStatus,
    BusinessRuleError,
    MeetingType,
    UserProfile,
)
from app.core.scheduling import BusySource
from app.integrations.google_calendar import GoogleCalendarClient, GoogleCalendarConfirmationGateway
from app.integrations.google_calendar.entities import GoogleOAuthTokens
from app.settings.config import Settings

MOSCOW = ZoneInfo("Europe/Moscow")


class FakeRequest:
    def __init__(self, response: dict | None = None) -> None:
        self.response = response or {}

    def execute(self) -> dict:
        return self.response


class FakeFreebusyResource:
    def __init__(self, service: "FakeCalendarService") -> None:
        self.service = service

    def query(self, *, body: dict) -> FakeRequest:
        self.service.freebusy_body = body
        return FakeRequest(self.service.freebusy_response)


class FakeEventsResource:
    def __init__(self, service: "FakeCalendarService") -> None:
        self.service = service

    def insert(self, *, calendarId: str, body: dict, sendUpdates: str) -> FakeRequest:
        self.service.insert_args = {
            "calendarId": calendarId,
            "body": body,
            "sendUpdates": sendUpdates,
        }
        return FakeRequest({"id": "event-123"})

    def delete(self, *, calendarId: str, eventId: str, sendUpdates: str) -> FakeRequest:
        self.service.delete_args = {
            "calendarId": calendarId,
            "eventId": eventId,
            "sendUpdates": sendUpdates,
        }
        return FakeRequest()


class FakeCalendarService:
    def __init__(self) -> None:
        self.freebusy_response = {
            "calendars": {
                "primary": {
                    "busy": [
                        {
                            "start": "2026-07-10T12:00:00+03:00",
                            "end": "2026-07-10T13:00:00+03:00",
                        }
                    ]
                }
            }
        }
        self.freebusy_body: dict | None = None
        self.insert_args: dict | None = None
        self.delete_args: dict | None = None

    def freebusy(self) -> FakeFreebusyResource:
        return FakeFreebusyResource(self)

    def events(self) -> FakeEventsResource:
        return FakeEventsResource(self)


def test_google_calendar_freebusy_maps_to_busy_intervals() -> None:
    service = FakeCalendarService()
    client = _client(service)

    intervals = client.list_busy_intervals(
        time_min=datetime(2026, 7, 10, 10, 0, tzinfo=MOSCOW),
        time_max=datetime(2026, 7, 10, 18, 0, tzinfo=MOSCOW),
    )

    assert len(intervals) == 1
    assert intervals[0].source == BusySource.CALENDAR
    assert intervals[0].starts_at == datetime(2026, 7, 10, 12, 0, tzinfo=MOSCOW)
    assert service.freebusy_body["items"] == [{"id": "primary"}]


def test_google_calendar_create_event_contains_mvp_fields() -> None:
    service = FakeCalendarService()
    client = _client(service)
    booking = _booking()
    user = UserProfile(telegram_id=1001, full_name="Ирина", email="client@example.com")
    meeting_type = MeetingType(name="Консультация", allowed_durations_minutes=(30, 60))

    event_id = client.create_event(
        booking=booking,
        user=user,
        meeting_type=meeting_type,
        meeting_url="https://telemost.example/meeting",
    )

    assert event_id == "event-123"
    assert service.insert_args["calendarId"] == "primary"
    assert service.insert_args["sendUpdates"] == "all"
    body = service.insert_args["body"]
    assert body["location"] == "https://telemost.example/meeting"
    assert {"email": "client@example.com"} in body["attendees"]
    assert {"email": "admin@example.com"} in body["attendees"]
    assert "https://telemost.example/meeting" in body["description"]
    assert body["reminders"]["overrides"] == [
        {"method": "email", "minutes": 1440},
        {"method": "popup", "minutes": 60},
    ]


@pytest.mark.asyncio
async def test_confirmation_gateway_rejects_busy_calendar_slot() -> None:
    service = FakeCalendarService()
    gateway = GoogleCalendarConfirmationGateway(_client(service))

    with pytest.raises(BusinessRuleError) as error:
        await gateway.confirm_booking(
            booking=_booking(),
            user=UserProfile(telegram_id=1001, email="client@example.com"),
            meeting_type=MeetingType(name="Консультация", allowed_durations_minutes=(30,)),
            meeting_url="https://telemost.example/meeting",
        )

    assert error.value.rule == "calendar_conflict"
    assert service.insert_args is None


def _client(service: FakeCalendarService) -> GoogleCalendarClient:
    settings = Settings(
        google_admin_email="admin@example.com",
        google_calendar_id="primary",
    )
    tokens = GoogleOAuthTokens(
        access_token=SecretStr("access"),
        refresh_token=SecretStr("refresh"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id="client-id",
        client_secret=SecretStr("client-secret"),
    )
    return GoogleCalendarClient(
        settings=settings,
        token_provider=lambda: tokens,
        service_factory=lambda _: service,
    )


def _booking() -> BookingRecord:
    return BookingRecord(
        user_id=UserProfile(telegram_id=1001).id,
        meeting_type_id=MeetingType(name="Консультация", allowed_durations_minutes=(30,)).id,
        duration_minutes=30,
        starts_at=datetime(2026, 7, 10, 12, 0, tzinfo=MOSCOW),
        ends_at=datetime(2026, 7, 10, 12, 30, tzinfo=MOSCOW),
        status=BookingStatus.PENDING,
        user_comment="Обсудить проект",
    )
