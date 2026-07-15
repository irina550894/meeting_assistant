from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.booking import BookingRecord, BookingStatus, MeetingType, UserProfile
from app.interfaces.http.dependencies import get_current_mini_app_user, get_user_booking_use_cases
from app.main import create_app

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


class FakeUserUseCases:
    def __init__(self):
        self.meeting_type = MeetingType(
            id=uuid4(),
            name="Consultation",
            allowed_durations_minutes=(30, 60),
        )
        self.booking = BookingRecord(
            id=uuid4(),
            user_id=USER.id,
            meeting_type_id=self.meeting_type.id,
            duration_minutes=60,
            starts_at=NOW + timedelta(days=2),
            ends_at=NOW + timedelta(days=2, hours=1),
            status=BookingStatus.PENDING,
            created_at=NOW,
            updated_at=NOW,
        )

    async def accept_consent(self, user):
        user.consent_accepted_at = NOW
        user.consent_url = "https://example.com/consent"
        user.policy_url = "https://example.com/policy"
        return user

    async def list_meeting_types(self):
        return [self.meeting_type]

    async def available_dates(self):
        return [(NOW + timedelta(days=1)).date()]

    async def available_slots(self, *, target_date, meeting_type_id, duration_minutes):
        starts_at = datetime.combine(target_date, datetime.min.time(), tzinfo=UTC)
        return [
            type(
                "Slot",
                (),
                {"starts_at": starts_at, "ends_at": starts_at + timedelta(hours=1)},
            )
        ]

    async def create_booking(self, *, user, draft):
        return self.booking

    async def list_user_bookings(self, user):
        return [self.booking]

    async def get_user_booking(self, *, user, booking_id):
        return self.booking

    async def cancel_user_booking(self, *, user, booking_id, reason=None):
        self.booking.status = BookingStatus.CANCELLED_BY_USER
        self.booking.cancellation_reason = reason
        return self.booking

    async def prepare_reschedule(self, *, user, booking_id):
        return self.booking


USER = UserProfile(
    id=uuid4(),
    telegram_id=1001,
    telegram_username="client",
    full_name="Client",
    email="client@example.com",
)


async def current_user_override():
    return USER


def user_api_client() -> tuple[TestClient, FakeUserUseCases]:
    app = create_app()
    fake_use_cases = FakeUserUseCases()
    app.dependency_overrides[get_current_mini_app_user] = current_user_override
    app.dependency_overrides[get_user_booking_use_cases] = lambda: fake_use_cases
    return TestClient(app), fake_use_cases


def test_profile_returns_current_user() -> None:
    client, _ = user_api_client()

    response = client.get("/api/miniapp/profile")

    assert response.status_code == 200
    assert response.json()["telegram_id"] == 1001
    assert response.json()["telegram_username"] == "client"


def test_meeting_types_returns_active_items() -> None:
    client, use_cases = user_api_client()

    response = client.get("/api/miniapp/meeting-types")

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == str(use_cases.meeting_type.id)
    assert response.json()["items"][0]["allowed_durations_minutes"] == [30, 60]


def test_create_list_and_cancel_booking() -> None:
    client, use_cases = user_api_client()

    create_response = client.post(
        "/api/miniapp/bookings",
        json={
            "full_name": "Client",
            "email": "client@example.com",
            "meeting_type_id": str(use_cases.meeting_type.id),
            "duration_minutes": 60,
            "starts_at": (NOW + timedelta(days=2)).isoformat(),
            "ends_at": (NOW + timedelta(days=2, hours=1)).isoformat(),
            "user_comment": "Discuss project",
        },
    )
    list_response = client.get("/api/miniapp/bookings")
    cancel_response = client.post(
        f"/api/miniapp/bookings/{use_cases.booking.id}/cancel",
        json={"reason": "Cannot attend"},
    )

    assert create_response.status_code == 200
    assert create_response.json()["booking"]["id"] == str(use_cases.booking.id)
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["id"] == str(use_cases.booking.id)
    assert cancel_response.status_code == 200
    assert cancel_response.json()["booking"]["status"] == "cancelled_by_user"
    assert cancel_response.json()["booking"]["cancellation_reason"] == "Cannot attend"


def test_profile_requires_session_cookie_without_override() -> None:
    client = TestClient(create_app())

    response = client.get("/api/miniapp/profile")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "mini_app_session_missing"
