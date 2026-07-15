from datetime import UTC, datetime, timedelta

import pytest

from app.application import UserBookingUseCaseDeps, UserBookingUseCases
from app.core.booking import BookingRecord, BookingService, BookingStatus, MeetingType
from app.core.user_flow import BookingDraft, UserFlowService
from app.settings.config import Settings

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


class FakeUsers:
    async def save(self, user):
        self.user = user


class FakeMeetingTypes:
    def __init__(self, meeting_type: MeetingType):
        self.meeting_type = meeting_type

    async def list_active(self):
        return [self.meeting_type]

    async def get(self, meeting_type_id):
        if meeting_type_id == self.meeting_type.id:
            return self.meeting_type
        return None


class FakeBookings:
    def __init__(self):
        self.bookings = []
        self.audit_entries = []
        self.saved_result = None

    async def list_by_user(self, user_id):
        return [booking for booking in self.bookings if booking.user_id == user_id]

    async def get_for_user(self, booking_id, user_id):
        for booking in self.bookings:
            if booking.id == booking_id and booking.user_id == user_id:
                return booking
        return None

    async def save_booking_result(self, result):
        self.saved_result = result
        self.bookings.append(result.booking)
        self.audit_entries.extend(result.audit_entries)

    async def save_booking(self, booking):
        return None

    async def save_audit_entries(self, entries):
        self.audit_entries.extend(entries)


class FakeSchedule:
    pass


class FakeNotifier:
    def __init__(self):
        self.created = []
        self.cancelled = []

    async def booking_created(self, booking):
        self.created.append(booking)

    async def booking_cancelled_by_user(self, booking):
        self.cancelled.append(booking)

    async def reschedule_requested(self, booking):
        self.created.append(booking)


class FakeBackgroundJobs:
    def __init__(self):
        self.created = []

    async def schedule_booking_created(self, booking, *, now):
        self.created.append((booking, now))


def clock() -> datetime:
    return NOW


def consented_user(service: BookingService):
    user = service.create_or_update_user(
        telegram_id=1001,
        telegram_username="client",
        now=NOW,
    )
    service.accept_personal_data_consent(
        user,
        consent_url="https://example.com/consent",
        policy_url="https://example.com/policy",
        now=NOW,
    )
    return user


def use_cases(
    *,
    meeting_type: MeetingType,
    bookings: FakeBookings,
    notifier: FakeNotifier | None = None,
    background_jobs: FakeBackgroundJobs | None = None,
) -> UserBookingUseCases:
    booking_service = BookingService()
    return UserBookingUseCases(
        UserBookingUseCaseDeps(
            settings=Settings(
                personal_data_consent_url="https://example.com/consent",
                personal_data_policy_url="https://example.com/policy",
            ),
            users=FakeUsers(),
            meeting_types=FakeMeetingTypes(meeting_type),
            bookings=bookings,
            schedule=FakeSchedule(),
            flow=UserFlowService(
                booking_service=booking_service,
                check_email_deliverability=False,
            ),
            booking_service=booking_service,
            clock=clock,
            notifier=notifier,
            background_jobs=background_jobs,
        )
    )


@pytest.mark.asyncio
async def test_create_booking_saves_result_schedules_job_and_notifies() -> None:
    meeting_type = MeetingType(name="Consultation", allowed_durations_minutes=(60,))
    bookings = FakeBookings()
    notifier = FakeNotifier()
    background_jobs = FakeBackgroundJobs()
    service = BookingService()
    user = consented_user(service)
    draft = BookingDraft(
        full_name="Client",
        email="client@example.com",
        meeting_type_id=meeting_type.id,
        duration_minutes=60,
        selected_date=(NOW + timedelta(days=2)).date(),
        starts_at=NOW + timedelta(days=2),
        ends_at=NOW + timedelta(days=2, hours=1),
    )

    booking = await use_cases(
        meeting_type=meeting_type,
        bookings=bookings,
        notifier=notifier,
        background_jobs=background_jobs,
    ).create_booking(user=user, draft=draft)

    assert booking.status == BookingStatus.PENDING
    assert booking.created_source == "mini_app"
    assert {entry.source for entry in bookings.audit_entries} == {"mini_app"}
    assert bookings.saved_result is not None
    assert notifier.created == [booking]
    assert background_jobs.created[0][0] == booking


@pytest.mark.asyncio
async def test_cancel_user_booking_saves_audit_and_notifies() -> None:
    meeting_type = MeetingType(name="Consultation", allowed_durations_minutes=(60,))
    bookings = FakeBookings()
    notifier = FakeNotifier()
    service = BookingService()
    user = consented_user(service)
    booking = BookingRecord(
        user_id=user.id,
        meeting_type_id=meeting_type.id,
        duration_minutes=60,
        starts_at=NOW + timedelta(days=2),
        ends_at=NOW + timedelta(days=2, hours=1),
        status=BookingStatus.PENDING,
    )
    bookings.bookings.append(booking)

    result = await use_cases(
        meeting_type=meeting_type,
        bookings=bookings,
        notifier=notifier,
    ).cancel_user_booking(user=user, booking_id=booking.id)

    assert result.status == BookingStatus.CANCELLED_BY_USER
    assert bookings.audit_entries[-1].action == "booking_cancelled_by_user"
    assert bookings.audit_entries[-1].source == "mini_app"
    assert notifier.cancelled == [booking]
