from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.core.admin_flow import AdminBookingCard
from app.core.booking import BookingRecord, BookingStatus, MeetingType, UserProfile
from app.integrations.telegram.ports import (
    AdminMeetingType,
    AdminScheduleRestriction,
    AdminScheduleSettings,
    AdminWorkingHoursRule,
)
from app.interfaces.http.dependencies import (
    get_admin_booking_use_cases,
    get_admin_settings_use_cases,
    get_current_mini_app_admin,
)
from app.main import create_app

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


ADMIN = UserProfile(
    id=uuid4(),
    telegram_id=5001,
    telegram_username="admin",
    full_name="Admin",
    email="admin@example.com",
)

CLIENT = UserProfile(
    id=uuid4(),
    telegram_id=1001,
    telegram_username="client",
    full_name="Client",
    email="client@example.com",
)


class FakeAdminBookingUseCases:
    def __init__(self) -> None:
        self.meeting_type = MeetingType(
            id=uuid4(),
            name="Consultation",
            allowed_durations_minutes=(30, 60),
        )
        self.pending_booking = BookingRecord(
            id=uuid4(),
            display_number=8,
            user_id=CLIENT.id,
            meeting_type_id=self.meeting_type.id,
            duration_minutes=60,
            starts_at=NOW + timedelta(days=2),
            ends_at=NOW + timedelta(days=2, hours=1),
            status=BookingStatus.PENDING,
            created_at=NOW,
            updated_at=NOW,
        )
        self.confirmed_booking = BookingRecord(
            id=uuid4(),
            display_number=9,
            user_id=CLIENT.id,
            meeting_type_id=self.meeting_type.id,
            duration_minutes=30,
            starts_at=NOW + timedelta(days=3),
            ends_at=NOW + timedelta(days=3, minutes=30),
            status=BookingStatus.CONFIRMED,
            meeting_url="https://meet.example.com/current",
            created_at=NOW,
            updated_at=NOW,
        )

    async def dashboard(self):
        return type(
            "Dashboard",
            (),
            {
                "pending": 1,
                "confirmed": 1,
                "reschedule_requested": 0,
                "cancelled": 0,
                "upcoming": [self.confirmed_booking],
                "recent_pending": [self.pending_booking],
            },
        )()

    async def list_bookings(self, *, status=None):
        bookings = [self.pending_booking, self.confirmed_booking]
        if status is not None:
            return [booking for booking in bookings if booking.status == status]
        return bookings

    async def get_booking_card(self, booking_id: UUID):
        booking = self.pending_booking
        if booking_id == self.confirmed_booking.id:
            booking = self.confirmed_booking
        return AdminBookingCard(
            booking=booking,
            user=CLIENT,
            meeting_type=self.meeting_type,
        )

    async def confirm_booking(self, *, booking_id: UUID, meeting_url: str, admin_telegram_id: int):
        self.pending_booking.status = BookingStatus.CONFIRMED
        self.pending_booking.meeting_url = meeting_url
        return await self.get_booking_card(booking_id)

    async def reject_booking(self, *, booking_id: UUID, admin_telegram_id: int, reason=None):
        self.pending_booking.status = BookingStatus.REJECTED
        self.pending_booking.rejection_reason = reason
        return await self.get_booking_card(booking_id)

    async def cancel_booking(self, *, booking_id: UUID, admin_telegram_id: int, reason=None):
        self.confirmed_booking.status = BookingStatus.CANCELLED_BY_USER
        self.confirmed_booking.cancellation_reason = reason
        return await self.get_booking_card(booking_id)


class FakeAdminSettingsUseCases:
    def __init__(self) -> None:
        self.restriction_id = uuid4()
        self.meeting_type = AdminMeetingType(
            id=uuid4(),
            name="Audit",
            allowed_durations_minutes=(45,),
            is_fixed_duration=True,
            is_active=True,
        )

    async def get_schedule_settings(self):
        return AdminScheduleSettings(
            timezone="Europe/Moscow",
            min_booking_lead_days=1,
            booking_horizon_days=30,
            slot_step_minutes=30,
            meeting_buffer_minutes=15,
        )

    async def update_schedule_settings(
        self,
        *,
        booking_horizon_days: int,
        slot_step_minutes: int,
        meeting_buffer_minutes: int,
    ):
        self.last_booking_horizon_days = booking_horizon_days
        self.last_slot_step_minutes = slot_step_minutes
        self.last_meeting_buffer_minutes = meeting_buffer_minutes
        return AdminScheduleSettings(
            timezone="Europe/Moscow",
            min_booking_lead_days=1,
            booking_horizon_days=booking_horizon_days,
            slot_step_minutes=slot_step_minutes,
            meeting_buffer_minutes=meeting_buffer_minutes,
        )

    async def list_working_hours(self):
        return [
            AdminWorkingHoursRule(
                weekday=1,
                is_working_day=True,
                start_time=time(10, 0),
                end_time=time(18, 0),
            )
        ]

    async def update_working_hours(
        self,
        *,
        weekday: int,
        is_working_day: bool,
        start_time: time | None,
        end_time: time | None,
    ):
        if is_working_day and (start_time is None or end_time is None or start_time >= end_time):
            from app.application import AdminSettingsUseCaseError

            raise AdminSettingsUseCaseError(
                "invalid_working_hours",
                "Working day start time must be before end time.",
            )
        self.last_weekday = weekday
        self.last_is_working_day = is_working_day
        self.last_start_time = start_time
        self.last_end_time = end_time
        return AdminWorkingHoursRule(
            weekday=weekday,
            is_working_day=is_working_day,
            start_time=start_time,
            end_time=end_time,
        )

    async def list_restrictions(self, *, from_date: date):
        return [
            AdminScheduleRestriction(
                id=self.restriction_id,
                restriction_date=from_date,
                restriction_type="closed_day",
                admin_comment="Day off",
            )
        ]

    async def add_closed_day_restriction(
        self,
        *,
        restriction_date: date,
        admin_comment: str | None,
    ):
        self.last_restriction_date = restriction_date
        self.last_admin_comment = admin_comment

    async def add_time_interval_restriction(
        self,
        *,
        restriction_date: date,
        start_time: time,
        end_time: time,
        admin_comment: str | None,
    ):
        self.last_time_interval_date = restriction_date
        self.last_time_interval_start = start_time
        self.last_time_interval_end = end_time
        self.last_time_interval_comment = admin_comment

    async def delete_restriction(self, restriction_id: UUID):
        self.deleted_restriction_id = restriction_id

    async def list_meeting_types_admin(self):
        return [self.meeting_type]

    async def add_meeting_type(
        self,
        *,
        name: str,
        allowed_durations_minutes: tuple[int, ...],
        is_fixed_duration: bool,
    ):
        self.meeting_type = AdminMeetingType(
            id=uuid4(),
            name=name,
            allowed_durations_minutes=allowed_durations_minutes,
            is_fixed_duration=is_fixed_duration,
            is_active=True,
        )
        return self.meeting_type

    async def set_meeting_type_active(self, meeting_type_id: UUID, *, is_active: bool):
        self.last_meeting_type_id = meeting_type_id
        self.last_is_active = is_active


async def current_admin_override():
    return ADMIN


def admin_api_client() -> tuple[TestClient, FakeAdminBookingUseCases, FakeAdminSettingsUseCases]:
    app = create_app()
    booking_use_cases = FakeAdminBookingUseCases()
    settings_use_cases = FakeAdminSettingsUseCases()
    app.dependency_overrides[get_current_mini_app_admin] = current_admin_override
    app.dependency_overrides[get_admin_booking_use_cases] = lambda: booking_use_cases
    app.dependency_overrides[get_admin_settings_use_cases] = lambda: settings_use_cases
    return TestClient(app), booking_use_cases, settings_use_cases


def test_admin_dashboard_returns_metrics_and_lists() -> None:
    client, booking_use_cases, _ = admin_api_client()

    response = client.get("/api/miniapp/admin/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["metrics"]["pending"] == 1
    assert body["metrics"]["confirmed"] == 1
    assert body["upcoming"][0]["id"] == str(booking_use_cases.confirmed_booking.id)
    assert body["upcoming"][0]["display_number"] == 9
    assert body["recent_pending"][0]["id"] == str(booking_use_cases.pending_booking.id)
    assert body["recent_pending"][0]["display_number"] == 8


def test_admin_list_bookings_can_filter_by_status() -> None:
    client, booking_use_cases, _ = admin_api_client()

    response = client.get("/api/miniapp/admin/bookings?status=pending")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["booking"]["id"] == str(booking_use_cases.pending_booking.id)
    assert items[0]["booking"]["display_number"] == 8
    assert items[0]["user"]["telegram_id"] == CLIENT.telegram_id
    assert items[0]["meeting_type"]["allowed_durations_minutes"] == [30, 60]


def test_admin_list_bookings_rejects_invalid_status_filter() -> None:
    client, _, _ = admin_api_client()

    response = client.get("/api/miniapp/admin/bookings?status=bad")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_booking_status"


def test_admin_confirm_and_reject_booking() -> None:
    client, booking_use_cases, _ = admin_api_client()

    confirm_response = client.post(
        f"/api/miniapp/admin/bookings/{booking_use_cases.pending_booking.id}/confirm",
        json={"meeting_url": "https://meet.example.com/new"},
    )
    reject_response = client.post(
        f"/api/miniapp/admin/bookings/{booking_use_cases.pending_booking.id}/reject",
        json={"reason": "No capacity"},
    )

    assert confirm_response.status_code == 200
    assert confirm_response.json()["booking"]["status"] == "confirmed"
    assert confirm_response.json()["booking"]["meeting_url"] == "https://meet.example.com/new"
    assert reject_response.status_code == 200
    assert reject_response.json()["booking"]["status"] == "rejected"
    assert reject_response.json()["booking"]["rejection_reason"] == "No capacity"


def test_admin_cancel_confirmed_booking() -> None:
    client, booking_use_cases, _ = admin_api_client()

    response = client.post(
        f"/api/miniapp/admin/bookings/{booking_use_cases.confirmed_booking.id}/cancel",
        json={"reason": "Client asked to cancel"},
    )

    assert response.status_code == 200
    assert response.json()["booking"]["status"] == "cancelled_by_user"
    assert response.json()["booking"]["cancellation_reason"] == "Client asked to cancel"


def test_admin_schedule_settings_restrictions_and_working_hours() -> None:
    client, _, settings_use_cases = admin_api_client()

    settings_response = client.get("/api/miniapp/admin/schedule/settings")
    settings_update_response = client.patch(
        "/api/miniapp/admin/schedule/settings",
        json={
            "booking_horizon_days": 45,
            "slot_step_minutes": 30,
            "meeting_buffer_minutes": 20,
        },
    )
    working_hours_response = client.get("/api/miniapp/admin/schedule/working-hours")
    working_hours_update_response = client.patch(
        "/api/miniapp/admin/schedule/working-hours/1",
        json={"is_working_day": True, "start_time": "11:00", "end_time": "17:30"},
    )
    restrictions_response = client.get("/api/miniapp/admin/schedule/restrictions?from=2026-07-20")
    create_response = client.post(
        "/api/miniapp/admin/schedule/restrictions/closed-day",
        json={"restriction_date": "2026-07-25", "admin_comment": "Vacation"},
    )
    create_time_response = client.post(
        "/api/miniapp/admin/schedule/restrictions/time-interval",
        json={
            "restriction_date": "2026-07-26",
            "start_time": "13:00",
            "end_time": "15:30",
            "admin_comment": "Busy",
        },
    )
    delete_response = client.delete(
        f"/api/miniapp/admin/schedule/restrictions/{settings_use_cases.restriction_id}"
    )

    assert settings_response.status_code == 200
    assert settings_response.json()["timezone"] == "Europe/Moscow"
    assert settings_update_response.status_code == 200
    assert settings_update_response.json()["booking_horizon_days"] == 45
    assert settings_use_cases.last_booking_horizon_days == 45
    assert settings_use_cases.last_slot_step_minutes == 30
    assert settings_use_cases.last_meeting_buffer_minutes == 20
    assert working_hours_response.status_code == 200
    assert working_hours_response.json()["items"][0]["weekday"] == 1
    assert working_hours_update_response.status_code == 200
    assert working_hours_update_response.json()["start_time"] == "11:00:00"
    assert settings_use_cases.last_weekday == 1
    assert settings_use_cases.last_start_time == time(11, 0)
    assert settings_use_cases.last_end_time == time(17, 30)
    assert restrictions_response.status_code == 200
    assert restrictions_response.json()["items"][0]["restriction_type"] == "closed_day"
    assert create_response.status_code == 200
    assert settings_use_cases.last_restriction_date == date(2026, 7, 25)
    assert create_time_response.status_code == 200
    assert settings_use_cases.last_time_interval_date == date(2026, 7, 26)
    assert settings_use_cases.last_time_interval_start == time(13, 0)
    assert settings_use_cases.last_time_interval_end == time(15, 30)
    assert settings_use_cases.last_time_interval_comment == "Busy"
    assert delete_response.status_code == 200
    assert settings_use_cases.deleted_restriction_id == settings_use_cases.restriction_id


def test_admin_time_interval_rejects_invalid_range() -> None:
    client, _, _ = admin_api_client()

    response = client.post(
        "/api/miniapp/admin/schedule/restrictions/time-interval",
        json={
            "restriction_date": "2026-07-26",
            "start_time": "16:00",
            "end_time": "15:00",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "invalid_time_interval"


def test_admin_working_hours_rejects_invalid_range() -> None:
    client, _, _ = admin_api_client()

    response = client.patch(
        "/api/miniapp/admin/schedule/working-hours/1",
        json={"is_working_day": True, "start_time": "18:00", "end_time": "10:00"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "invalid_working_hours"


def test_admin_meeting_types_list_create_and_toggle() -> None:
    client, _, settings_use_cases = admin_api_client()

    list_response = client.get("/api/miniapp/admin/meeting-types")
    create_response = client.post(
        "/api/miniapp/admin/meeting-types",
        json={
            "name": "Planning",
            "allowed_durations_minutes": [30, 90],
            "is_fixed_duration": False,
        },
    )
    meeting_type_id = create_response.json()["id"]
    update_response = client.patch(
        f"/api/miniapp/admin/meeting-types/{meeting_type_id}",
        json={"is_active": False},
    )

    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["name"] == "Audit"
    assert create_response.status_code == 200
    assert create_response.json()["allowed_durations_minutes"] == [30, 90]
    assert update_response.status_code == 200
    assert settings_use_cases.last_meeting_type_id == UUID(meeting_type_id)
    assert settings_use_cases.last_is_active is False


def test_admin_dashboard_requires_admin_session_without_override() -> None:
    client = TestClient(create_app())

    response = client.get("/api/miniapp/admin/dashboard")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "mini_app_session_missing"
